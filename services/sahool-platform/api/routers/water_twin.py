"""api/routers/water_twin.py — توأم المياه مُغذّى بدفتر المياه (المرحلة الثانية)

يُكمِّل نقطة ``/api/v1/scenario/water-twin`` النقيّة (المرحلة الأولى) بنقطة **field-scoped**
تستثمر **دفتر المياه اليوميّ v98**: تقرأ أحدث صفوف الدفتر للحقل (RLS) فتشتقّ منها الحالة
الابتدائيّة (النضوب) وتقدير ETc اليوميّ، ثمّ تحاكي «ماذا لو أخّرت/خفّضت الريّ؟» للأفق الأماميّ.

صدق منهجيّ صارم:
  - الاشتقاق من الدفتر فقط (``api/water_twin_seed.py`` النقيّ) — **لا اختراع أرقام**؛ غياب
    مصدر الاشتقاق ⇒ **422 صادق** يطلب مدخلاً صريحاً (لا حالة مُلفّقة).
  - **TAW/RAW** يُمرَّران صراحةً (إقرار زراعيّ)، أو **يُشتقّان ديناميكيّاً من عمق الجذور Zr**
    (محصول الحقل + عمره + قوام التربة) عبر دوالّ ``core/engines/fao56.py`` النقيّة: غياب
    بطاقة المحصول ⇒ **422 صادق** يطلب ``taw_mm`` صريحاً (لا تخمين). المصدر مُعلَن (``taw_source``).
  - **مصدر كلّ قيمة مُعلَن** في الردّ (``seed.*_source`` · ``taw_source``) للتدقيق.
  - الفيزياء كلّها في المحرّك النقيّ ``api/water_twin.py`` + ``core/engines/fao56.py`` (FAO-56) —
    هذا الموجِّه تنسيق فقط (لا يكرّر صيغة).
  - معزول بالمستأجِر (RLS، FIELD_VIEW)؛ حقل خارج المستأجِر ⇒ 404.

نمط الاستيراد من ``api.main`` يطابق ``routers/water_ledger.py``: التبعيّات تبقى في ``main``
ويستوردها هذا الموجِّه، و``api.main`` يستورده في نهايته فقط (يُحلّ الاستيراد الدائريّ).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

from core.engines.fao56 import root_depth_for_crop, taw_from_root_depth
from core.season_phenology import crop_kc_profile, resolve_crop_id
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from api.main import (
    _DB_POOL,
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.water_ledger_compute import LEDGER_SELECT_COLS, row_to_ledger_entry
from api.water_twin import DayPlan, compare_scenarios, delay_irrigation, scale_irrigation
from api.water_twin_seed import seed_daily_etc, seed_initial_depletion

logger = logging.getLogger(__name__)

router = APIRouter()


class FieldWaterTwinRequest(BaseModel):
    """طلب محاكاة توأم المياه لحقل، مُغذّى بالدفتر.

    ``taw_mm``/``raw_mm`` **اختياريّان**: إن غابا يُشتقّان ديناميكيّاً من عمق الجذور Zr
    (محصول الحقل + عمره + ``texture``) عبر دوالّ FAO-56 النقيّة؛ وإن تعذّر بناء بطاقة المحصول
    ⇒ 422 يطلب ``taw_mm`` صريحاً. ``initial_depletion_mm`` و``daily_etc_mm`` اختياريّان:
    إن غابا يُشتقّان من الدفتر؛ وإن تعذّر ⇒ 422 صادق.
    """

    taw_mm: float | None = Field(
        default=None, gt=0, description="إجماليّ الماء المتاح بمنطقة الجذور (وإلّا يُشتقّ من Zr)"
    )
    raw_mm: float | None = Field(
        default=None, gt=0, description="الماء المتاح بسهولة = p·TAW (وإلّا = taw·raw_fraction)"
    )
    texture: str = Field(default="loam", description="قوام التربة (لاشتقاق θFC/θWP — Table 19)")
    zr_min: float = Field(default=0.10, gt=0, description="أدنى عمق جذور Zr_min (m) عند الزراعة")
    zr_max: float = Field(default=1.0, gt=0, description="أقصى عمق جذور Zr_max (m) عند النضج")
    raw_fraction: float = Field(
        default=0.5, gt=0, le=1, description="نسبة الاستنزاف المسموح p (RAW = p·TAW)"
    )
    horizon_days: int = Field(default=7, ge=1, le=60, description="أفق المحاكاة الأماميّ")
    baseline_irrigation_mm: float = Field(
        default=0.0, ge=0, description="الريّ اليوميّ المخطّط (سيناريو الأساس)"
    )
    daily_rain_mm: float = Field(default=0.0, ge=0, description="مطر فعّال يوميّ متوقَّع")
    daily_etc_mm: float | None = Field(
        default=None, ge=0, description="ETc يوميّ صريح (وإلّا متوسّط الدفتر الأخير)"
    )
    initial_depletion_mm: float | None = Field(
        default=None, ge=0, description="نضوب ابتدائيّ صريح (وإلّا من أحدث صفّ دفتر)"
    )
    recent_days_window: int = Field(
        default=7, ge=1, le=60, description="عدد صفوف الدفتر الأخيرة لتقدير ETc"
    )
    scenario_kind: Literal["delay", "scale"] = "scale"
    delay_days: int = Field(default=0, ge=0)
    scale_factor: float = Field(default=0.8, ge=0)


def resolve_taw_raw(
    req: FieldWaterTwinRequest,
    crop: str | None,
    days_after_planting: float | None,
) -> tuple[float, float, dict]:
    """يحسم (TAW، RAW، بيانات المصدر) — صريحاً من الطلب أو ديناميكيّاً من عمق الجذور Zr.

    إن مُرِّر ``taw_mm`` ⇒ يُستخدَم كما هو (RAW = ``raw_mm`` أو ``taw·raw_fraction``) ومصدره
    ``"request"`` (السلوك القائم تماماً — لا انحدار). وإلّا يُشتقّ من Zr عبر دوالّ FAO-56 النقيّة:

        profile = crop_kc_profile(resolve_crop_id(crop))
        Zr      = root_depth_for_crop(profile, DAP, zr_min, zr_max)   # FAO-56 §8 نموّ خطّيّ
        TAW     = taw_from_root_depth(Zr, texture)                    # FAO-56 Eq.82
        RAW     = TAW · raw_fraction (p)

    صدق: تعذّر بناء البطاقة (محصول مجهول) أو غياب العمر ⇒ ``ValueError`` (يُترجَم 422 يطلب
    ``taw_mm`` صريحاً — لا تخمين). Zr/θ تقديريّة تحتاج معايرة (موروث من docstrings المحرّك).
    """
    if req.taw_mm is not None:
        taw = req.taw_mm
        raw = req.raw_mm if req.raw_mm is not None else taw * req.raw_fraction
        return taw, raw, {"taw_source": "request", "root_depth_m": None, "notes": []}

    profile = crop_kc_profile(resolve_crop_id(crop))
    if profile is None:
        raise ValueError(
            f"تعذّر بناء بطاقة المحصول (المحصول: {crop or '—'}) لاشتقاق TAW من عمق الجذور — "
            "مرّر taw_mm صراحةً (لا تخمين)."
        )
    if days_after_planting is None:
        raise ValueError(
            "عمر المحصول مفقود (لا تاريخ زراعة للحقل) لاشتقاق TAW من عمق الجذور — مرّر taw_mm صراحةً."
        )
    zr = root_depth_for_crop(profile, days_after_planting, req.zr_min, req.zr_max)
    taw = taw_from_root_depth(zr, req.texture)
    if taw <= 0.0:
        raise ValueError(
            "TAW المُشتقّ من Zr = 0 (θFC≈θWP أو Zr=0) — مرّر taw_mm صراحةً أو راجِع قوام التربة."
        )
    raw = req.raw_mm if req.raw_mm is not None else taw * req.raw_fraction
    return (
        taw,
        raw,
        {
            "taw_source": "dynamic_zr",
            "root_depth_m": round(zr, 3),
            "notes": [
                "TAW مُشتقّ من عمق الجذور Zr (FAO-56 §8 + Eq.82): "
                "Zr/θFC/θWP تقديريّة نوعيّة تحتاج معايرة محلّيّة (لا قياسات موقعيّة).",
            ],
        },
    )


@router.post("/api/v1/fields/{field_id}/water-twin")
async def field_water_twin(
    req: FieldWaterTwinRequest,
    field_id: str = Path(..., description="معرّف الحقل لمحاكاة توأم مياهه"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """يحاكي توأم مياه الحقل مُغذّى بأحدث صفوف دفتره (RLS) — «ماذا لو أخّرت/خفّضت الريّ؟».

    يحسم TAW/RAW (صريحاً أو ديناميكيّاً من عمق الجذور Zr بمحصول الحقل وعمره)، يشتقّ النضوب
    الابتدائيّ + ETc من الدفتر (أو من تجاوزات الطلب الصريحة)، يبني جدول الأساس للأفق، يطبّق
    البديل (تأجيل/تحجيم)، ويقارن (أيّام إجهاد/استهلاك ماء). صدق: تعذّر اشتقاق TAW (بطاقة مفقودة
    ولا taw_mm) ⇒ 422 يطلب taw_mm صريحاً؛ تعذّر اشتقاق الحالة (لا دفتر ولا تجاوز) ⇒ 422؛ حقل
    خارج المستأجِر ⇒ 404؛ تعذّر القاعدة ⇒ 503.
    """
    # اقرأ أحدث صفوف الدفتر (DESC) + محصول/تاريخ زراعة الحقل (لاشتقاق Zr عند غياب taw_mm).
    recent: list[dict] = []
    crop_name: str | None = None
    planting_date = None
    if _DB_POOL is not None:
        try:
            async with tenant_connection(user) as conn:
                await _assert_field_in_tenant(conn, field_id)
                field_row = await conn.fetchrow(
                    "SELECT crop, planting_date FROM fields WHERE field_id = $1", field_id
                )
                rows = await conn.fetch(
                    f"SELECT {LEDGER_SELECT_COLS} FROM water_ledger "
                    "WHERE field_id = $1 ORDER BY ledger_date DESC LIMIT $2",
                    field_id,
                    req.recent_days_window,
                )
            recent = [row_to_ledger_entry(r) for r in rows]
            if field_row is not None:
                crop_name = field_row["crop"]
                planting_date = field_row["planting_date"]
        except HTTPException:
            raise  # 404 (حقل خارج المستأجِر) يصعد كما هو
        except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
            raise _db_unavailable("قراءة دفتر المياه لتوأم المياه", e) from e

    # العمر (الأيّام بعد الزراعة) لاشتقاق Zr — None إن غاب تاريخ الزراعة.
    das: float | None = None
    if planting_date is not None:
        das = (date.today() - planting_date).days
        if das < 0:
            raise HTTPException(status_code=422, detail="تاريخ الزراعة في المستقبل (عمر سالب).")

    # حسم TAW/RAW: صريحاً (السلوك القائم) أو ديناميكيّاً من Zr — مصدره مُعلَن في الردّ.
    try:
        taw_mm, raw_mm, taw_meta = resolve_taw_raw(req, crop_name, das)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    if raw_mm > taw_mm:
        raise HTTPException(status_code=422, detail="RAW يجب أن يكون ≤ TAW.")

    latest_row = recent[0] if recent else None
    init_dr, dr_source = seed_initial_depletion(latest_row, taw_mm, req.initial_depletion_mm)
    try:
        daily_etc, etc_source = seed_daily_etc(recent, req.daily_etc_mm)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    if init_dr is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "تعذّر اشتقاق النضوب الابتدائيّ: لا صفّ دفتر يحمل depletion_mm/soil_moisture_pct "
                "ولا initial_depletion_mm في الطلب. سجّل قيد دفتر أوّلاً أو مرّر القيمة صراحةً."
            ),
        )
    if daily_etc is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "تعذّر اشتقاق ETc: لا صفّ دفتر يحمل etc_mm ولا daily_etc_mm في الطلب. "
                "سجّل قيود دفتر أوّلاً أو مرّر القيمة صراحةً."
            ),
        )

    baseline = [
        DayPlan(daily_etc, req.daily_rain_mm, req.baseline_irrigation_mm)
        for _ in range(req.horizon_days)
    ]
    if req.scenario_kind == "delay":
        scenario = delay_irrigation(baseline, req.delay_days)
    else:  # scale
        scenario = scale_irrigation(baseline, req.scale_factor)

    try:
        result = compare_scenarios(taw_mm, raw_mm, init_dr, baseline, scenario)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    result["field_id"] = field_id
    result["seed"] = {
        "initial_depletion_mm": round(init_dr, 2),
        "initial_depletion_source": dr_source,
        "daily_etc_mm": round(daily_etc, 2),
        "daily_etc_source": etc_source,
        "ledger_rows_used": len(recent),
        "horizon_days": req.horizon_days,
    }
    result["taw_mm"] = round(taw_mm, 2)
    result["raw_mm"] = round(raw_mm, 2)
    result["taw_source"] = taw_meta["taw_source"]
    result["root_depth_m"] = taw_meta["root_depth_m"]
    if taw_meta["notes"]:
        result["taw_notes"] = taw_meta["notes"]
    return result
