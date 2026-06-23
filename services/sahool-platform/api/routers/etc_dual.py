"""api/routers/etc_dual.py — ETc المزدوج (FAO-56) لحقل، مُغذّى بـNDVI الحيّ.

يُغلق حلقة «Kc الديناميكيّ من NDVI» (#461): محرّك `compute_etc_dual` كان قادراً على اشتقاق Kcb
**رصداً** من NDVI لكنّه **غير مكشوف**. هذه النقطة field-scoped تجلب **NDVI الحقيقيّ المخزَّن للحقل**
(من أتمتة الصور) وتمرّره فعليّاً إلى المحرّك — فيرتبط قرار الماء بالقمر.

صدق منهجيّ:
  - **NDVI لا يُختلَق:** يُؤخَذ من `imagery_automation_fields.last_ndvi_mean` (عبر `gather_field_freshness`)
    أو من تجاوز صريح؛ غيابه ⇒ ``ndvi=None`` ⇒ Kcb عمريّ (المسار القائم) + ملاحظة (تدرّج لا خطأ).
  - **الطقس يمرّره المتّصِل** (متّسق مع نقاط scenario/irrigation-plan) — لا اعتماد شبكة جديد.
  - **المحصول/العمر/الملوحة** تُشتقّ من الحقل (بطاقة المحصول + تاريخ الزراعة + أحدث فحص تربة).
  - **مصدر كلّ قيمة مُعلَن** في الردّ (`ndvi.source`, `soil_ece_source`) + افتراضات المحرّك.
  - بطاقة محصول/عمر مفقودان ⇒ 422 صادق؛ حقل خارج المستأجِر ⇒ 404؛ القاعدة معطّلة ⇒ 503.

نمط الاستيراد من `api.main` يطابق `routers/water_twin.py` (يُحلّ الاستيراد الدائريّ: `api.main`
يستورد هذا الموجِّه في نهايته فقط). الفيزياء كلّها في `core/engines/fao56.py` — هذا تنسيق فقط.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date

from core.engines.fao56 import WeatherDay, compute_etc_dual
from core.season_phenology import crop_kc_profile, resolve_crop_id
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from api.field_state_projection import gather_field_freshness
from api.main import (
    _DB_POOL,
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class EtcDualRequest(BaseModel):
    """مدخل ETc المزدوج: طقس اليوم (يمرّره المتّصِل) + تجاوزات اختياريّة.

    NDVI والمحصول والعمر والملوحة تُحقَن من الحقل تلقائيّاً ما لم تُمرَّر صراحةً.
    """

    # الطقس (لـET0 — Penman-Monteith)
    temp_max_c: float
    temp_min_c: float
    humidity_pct: float = Field(..., ge=0, le=100)
    wind_speed_m_s: float = Field(..., ge=0)
    solar_radiation_mj_m2: float = Field(..., ge=0)
    latitude_deg: float = Field(..., ge=-90, le=90)
    elevation_m: float = 0.0
    day_of_year: int = Field(..., ge=1, le=366)
    # تجاوزات اختياريّة (الافتراضات FAO-56 موثّقة في المحرّك)
    de_mm: float = Field(default=0.0, ge=0, description="استنزاف الطبقة السطحيّة (مم)")
    texture: str = "loam"
    crop_height_m: float = Field(default=0.5, gt=0)
    fw: float = Field(default=1.0, ge=0, le=1, description="كسر السطح المبلّل (1=سطحيّ، ~0.3=تنقيط)")
    ndvi_bare: float = 0.15
    ndvi_full: float = 0.85
    # تجاوزات تسبق الحقن من الحقل (None ⇒ يُحقَن من الحقل)
    ndvi: float | None = Field(default=None, description="تجاوز NDVI (وإلّا أحدث NDVI مخزَّن للحقل)")
    soil_ece: float | None = Field(
        default=None, ge=0, description="تجاوز ملوحة التربة (وإلّا أحدث فحص)"
    )
    days_after_planting: int | None = Field(
        default=None, ge=0, description="تجاوز العمر (وإلّا من تاريخ الزراعة)"
    )


@router.post("/api/v1/fields/{field_id}/etc-dual")
async def field_etc_dual(
    req: EtcDualRequest,
    field_id: str = Path(..., description="معرّف الحقل"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """يحسب ETc المزدوج (FAO-56) للحقل مع Kcb مرصود من NDVI الحيّ حين يتوفّر.

    يقرأ الحقل (محصول/تاريخ زراعة) + أحدث NDVI/ملوحة مخزَّنة (RLS)، ويستدعي `compute_etc_dual`.
    صدق: NDVI مفقود ⇒ Kcb عمريّ (تدرّج معلَن)؛ بطاقة/عمر مفقودان ⇒ 422؛ القاعدة معطّلة ⇒ 503.
    """
    if _DB_POOL is None:
        raise HTTPException(status_code=503, detail="القاعدة غير مفعّلة (DATABASE_URL)")
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            field_row = await conn.fetchrow(
                "SELECT crop, planting_date FROM fields WHERE field_id = $1", field_id
            )
            freshness = await gather_field_freshness(conn, field_id)
    except HTTPException:
        raise  # 404 (حقل خارج المستأجِر) يصعد كما هو
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة الحقل لحساب ETc المزدوج", e) from e

    # 1. المحصول → بطاقة → CropKcProfile (إعادة استخدام مصدر الحقيقة)
    crop_name = field_row["crop"] if field_row else None
    crop_id = resolve_crop_id(crop_name)
    profile = crop_kc_profile(crop_id)
    if profile is None:
        raise HTTPException(
            status_code=422,
            detail=f"بطاقة محصول غير متوفّرة للحقل (المحصول: {crop_name or '—'}) — تعذّر حساب Kc.",
        )

    # 2. العمر (تجاوز الطلب يسبق تاريخ الزراعة)
    das = req.days_after_planting
    if das is None:
        planting = field_row["planting_date"] if field_row else None
        if planting is None:
            raise HTTPException(
                status_code=422,
                detail="تاريخ الزراعة مفقود — مرّر days_after_planting أو سجّل تاريخ الزراعة.",
            )
        das = (date.today() - planting).days
        if das < 0:
            raise HTTPException(status_code=422, detail="تاريخ الزراعة في المستقبل (عمر سالب).")

    # 3. NDVI الحيّ (جوهر الربط): تجاوز الطلب > المخزَّن > لا شيء (تدرّج صادق)
    stored_ndvi = freshness.get("ndvi_mean")
    if req.ndvi is not None:
        ndvi_used, ndvi_source = req.ndvi, "request"
    elif stored_ndvi is not None:
        ndvi_used, ndvi_source = float(stored_ndvi), "imagery_automation_fields"
    else:
        ndvi_used, ndvi_source = None, "none"
    ndvi_date = freshness.get("ndvi_date")

    # 4. الملوحة (تجاوز الطلب > أحدث فحص تربة > 0)
    if req.soil_ece is not None:
        soil_ece, soil_ece_source = req.soil_ece, "request"
    elif freshness.get("soil_ec") is not None:
        soil_ece, soil_ece_source = float(freshness["soil_ec"]), "soil_lab_tests"
    else:
        soil_ece, soil_ece_source = 0.0, "default"

    weather = WeatherDay(
        temp_max_c=req.temp_max_c,
        temp_min_c=req.temp_min_c,
        humidity_pct=req.humidity_pct,
        wind_speed_m_s=req.wind_speed_m_s,
        solar_radiation_mj_m2=req.solar_radiation_mj_m2,
        latitude_deg=req.latitude_deg,
        elevation_m=req.elevation_m,
        day_of_year=req.day_of_year,
    )
    try:
        result = compute_etc_dual(
            weather,
            profile,
            das,
            soil_ece=soil_ece,
            de_mm=req.de_mm,
            texture=req.texture,
            fw=req.fw,
            crop_height_m=req.crop_height_m,
            ndvi=ndvi_used,
            ndvi_bare=req.ndvi_bare,
            ndvi_full=req.ndvi_full,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"تعذّر حساب ETc المزدوج: {e}") from e

    if ndvi_used is None:
        result.assumptions.append("NDVI غير متاح للحقل ⇒ Kcb من العمر (تدرّج صادق، لا اختلاق)")

    payload = asdict(result)
    payload["field_id"] = field_id
    payload["ndvi"] = {
        "used": ndvi_used,
        "source": ndvi_source,
        "date": ndvi_date.isoformat() if hasattr(ndvi_date, "isoformat") else ndvi_date,
    }
    payload["inputs"] = {
        "crop_id": crop_id,
        "days_after_planting": das,
        "soil_ece": soil_ece,
        "soil_ece_source": soil_ece_source,
    }
    return payload
