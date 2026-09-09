"""api/routers/etc_dual.py — ETc المزدوج (FAO-56) لحقل، مُغذّى بـNDVI الحيّ + طقس Open-Meteo.

يُغلق حلقة «Kc الديناميكيّ من NDVI» (#461): محرّك `compute_etc_dual` كان قادراً على اشتقاق Kcb
**رصداً** من NDVI لكنّه **غير مكشوف**. هذه النقطة field-scoped تجلب **NDVI الحقيقيّ المخزَّن للحقل**
وتمرّره فعليّاً إلى المحرّك — فيرتبط قرار الماء بالقمر.

صدق منهجيّ:
  - **NDVI لا يُختلَق:** سلّم أولويّة صادق — تجاوز الطلب (`req.ndvi`) > **COG طازج** من
    raster-service (`/v1/fields/{id}/indicator-grid?index=ndvi&date=latest`، فقط إن
    `real_data=true`) > المخزَّن (`imagery_automation_fields.last_ndvi_mean` عبر
    `gather_field_freshness`) > لا شيء. أيّ تعذّر/`real_data=false` ⇒ تدرّج صامت للمخزَّن
    (لا خطأ، لا تعطيل النقطة). غيابه كلّه ⇒ ``ndvi=None`` ⇒ Kcb عمريّ + ملاحظة.
  - **الطقس ذاتيّ-الاكتفاء:** يُمرَّر كاملاً، أو يُجلب **حيّاً من Open-Meteo** بإحداثيّات الحقل؛
    تعذّر الجلب ولا طقس مُمرَّر ⇒ 503 صادق (لا اختلاق طقس). مصدر الطقس مُعلَن في الردّ.
  - **المحصول/العمر/الملوحة** تُشتقّ من الحقل (بطاقة المحصول + تاريخ الزراعة + أحدث فحص تربة).
  - **مصدر كلّ قيمة مُعلَن** (`weather_source`, `ndvi.source`, `soil_ece_source`) + افتراضات المحرّك.
  - بطاقة/عمر/إحداثيّات مفقودة ⇒ 422 صادق؛ حقل خارج المستأجِر ⇒ 404؛ القاعدة معطّلة ⇒ 503.

نمط الاستيراد من `api.main` يطابق `routers/water_twin.py`. الفيزياء كلّها في `core/engines/fao56.py`؛
جلب الطقس يتمّ **خارج** اتّصال القاعدة (لا حبس وصلة أثناء HTTP). هذا الموجِّه تنسيق فقط.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date

from core.engines.fao56 import WeatherDay, compute_etc_dual
from core.season_phenology import crop_kc_profile, resolve_crop_id
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from api import main as api_main
from api.field_state_projection import gather_field_freshness
from api.main import (
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.raster_service_client import get_indicator_grid
from api.weather_service_client import get_et0_product

logger = logging.getLogger(__name__)

router = APIRouter()

# مهلة قصيرة: NDVI الطازج تحسين لا حاجز — أيّ بطء/تعذّر ⇒ تدرّج صامت للمخزَّن.
_FRESH_NDVI_TIMEOUT_S = 8.0


class EtcDualRequest(BaseModel):
    """مدخل ETc المزدوج. **الطقس اختياريّ:** مرّره كاملاً، أو اتركه فيُجلب حيّاً من Open-Meteo.

    NDVI/المحصول/العمر/الملوحة/الإحداثيّات تُحقَن من الحقل تلقائيّاً ما لم تُمرَّر صراحةً.
    """

    # الطقس (لـET0 — Penman-Monteith). غياب temp_max_c ⇒ جلب حيّ من Open-Meteo بإحداثيّات الحقل.
    temp_max_c: float | None = None
    temp_min_c: float | None = None
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    wind_speed_m_s: float | None = Field(default=None, ge=0)
    solar_radiation_mj_m2: float | None = Field(default=None, ge=0)
    latitude_deg: float | None = Field(default=None, ge=-90, le=90)
    elevation_m: float | None = None
    day_of_year: int | None = Field(default=None, ge=1, le=366)
    # تجاوزات اختياريّة (الافتراضات FAO-56 موثّقة في المحرّك)
    de_mm: float = Field(default=0.0, ge=0, description="استنزاف الطبقة السطحيّة (مم)")
    texture: str = "loam"
    crop_height_m: float = Field(default=0.5, gt=0)
    fw: float = Field(default=1.0, ge=0, le=1, description="كسر السطح المبلّل (1=سطحيّ، ~0.3=تنقيط)")
    ndvi_bare: float = 0.15
    ndvi_full: float = 0.85
    # تجاوزات تسبق الحقن من الحقل (None ⇒ يُحقَن من الحقل)
    ndvi: float | None = Field(default=None, description="تجاوز NDVI (وإلّا طازج COG ثمّ مخزَّن)")
    prefer_fresh_ndvi: bool = Field(
        default=True,
        description="حاوِل جلب NDVI طازجاً من COG (raster-service) قبل المخزَّن؛ False ⇒ مخزَّن فقط.",
    )
    soil_ece: float | None = Field(
        default=None, ge=0, description="تجاوز ملوحة التربة (وإلّا أحدث فحص)"
    )
    days_after_planting: int | None = Field(
        default=None, ge=0, description="تجاوز العمر (وإلّا من تاريخ الزراعة)"
    )


def _today_doy() -> int:
    return date.today().timetuple().tm_yday


def _pick_ndvi(
    req_ndvi: float | None,
    fresh_ndvi: float | None,
    stored_ndvi: float | None,
) -> tuple[float | None, str]:
    """يختار NDVI ومصدره بسلّم أولويّة صادق (دالّة نقيّة قابلة للاختبار مباشرةً).

    الأولويّة: تجاوز الطلب (``req_ndvi``) > COG طازج (``fresh_ndvi``) > مخزَّن
    (``stored_ndvi``) > لا شيء. كلّ مدخل ``None`` يعني «غير متاح» فيُتدرَّج للتالي.
    يُرجِع ``(ndvi, source)`` حيث source ∈ {"request", "raster_fresh_cog",
    "imagery_automation_fields", "none"}. لا يخترع قيمة: الطازج يُمرَّر هنا فقط حين
    ثبت ``real_data=true`` عند الجلب (انظر ``_fetch_fresh_ndvi``).
    """
    if req_ndvi is not None:
        return req_ndvi, "request"
    if fresh_ndvi is not None:
        return float(fresh_ndvi), "raster_fresh_cog"
    if stored_ndvi is not None:
        return float(stored_ndvi), "imagery_automation_fields"
    return None, "none"


async def _fetch_fresh_ndvi(field_id: str) -> float | None:
    """يجلب NDVI الطازج من COG عبر raster-service (خارج اتّصال القاعدة، X-Agent-Token).

    يقرأ ``GET /v1/fields/{id}/indicator-grid?index=ndvi&date=latest`` الذي يقرأ COG
    حقيقيّاً ويُرجِع ``stats.mean`` + ``real_data``. **صدق:** يُرجِع المتوسّط فقط حين
    ``real_data is True`` (COG حقيقيّ)؛ أيّ تعذّر/``real_data=false``/شكل غير متوقَّع
    ⇒ ``None`` (تدرّج صامت للمخزَّن، لا خطأ، لا تعطيل النقطة، لا اختلاق).
    """
    try:
        data = await get_indicator_grid(
            field_id,
            index="ndvi",
            date="latest",
            timeout_s=_FRESH_NDVI_TIMEOUT_S,
        )
    except Exception as e:  # noqa: BLE001 — أيّ تعذّر شبكيّ/تحليل ⇒ تدرّج صامت
        logger.info("جلب NDVI الطازج تعذّر للحقل %s ⇒ تدرّج للمخزَّن: %s", field_id, e)
        return None

    if not isinstance(data, dict) or data.get("real_data") is not True:
        return None  # محاكاة/لا COG ⇒ لا نستخدمه (صدق: الطازج حقيقيّ فقط)
    mean = (data.get("stats") or {}).get("mean")
    if mean is None:
        return None
    try:
        return float(mean)
    except (TypeError, ValueError):
        return None


async def _resolve_weather(
    req: EtcDualRequest, field_lat: float | None, field_lon: float | None
) -> tuple[WeatherDay, str]:
    """يبني ``WeatherDay`` من الطلب (إن مُرِّر) أو يجلبه حيّاً من Open-Meteo (إحداثيّات الحقل).

    صدق: طقس ناقص جزئيّاً ⇒ 422 (مرّره كاملاً أو اتركه كلّه)؛ تعذّر Open-Meteo ⇒ 503 (لا اختلاق).
    يُرجِع ``(weather, source)`` حيث source ∈ {"request", "open-meteo"}.
    """
    # مسار الطلب: temp_max_c حاضر ⇒ يجب اكتمال المجموعة الأساسيّة.
    if req.temp_max_c is not None:
        required = {
            "temp_min_c": req.temp_min_c,
            "humidity_pct": req.humidity_pct,
            "wind_speed_m_s": req.wind_speed_m_s,
            "solar_radiation_mj_m2": req.solar_radiation_mj_m2,
        }
        missing = [k for k, v in required.items() if v is None]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"طقس ناقص ({missing}) — مرّر الطقس كاملاً أو اتركه كلّه للجلب الحيّ.",
            )
        lat = req.latitude_deg if req.latitude_deg is not None else field_lat
        if lat is None:
            raise HTTPException(
                status_code=422, detail="خطّ العرض مفقود (لا في الطلب ولا في الحقل)."
            )
        return (
            WeatherDay(
                temp_max_c=req.temp_max_c,
                temp_min_c=req.temp_min_c,
                humidity_pct=req.humidity_pct,
                wind_speed_m_s=req.wind_speed_m_s,
                solar_radiation_mj_m2=req.solar_radiation_mj_m2,
                latitude_deg=lat,
                elevation_m=(req.elevation_m if req.elevation_m is not None else 0.0),
                day_of_year=(req.day_of_year or _today_doy()),
            ),
            "request",
        )

    # مسار الجلب الحيّ: نحتاج إحداثيّات الحقل.
    if field_lat is None or field_lon is None:
        raise HTTPException(
            status_code=422,
            detail="إحداثيّات الحقل مفقودة — تعذّر جلب الطقس؛ مرّر الطقس صراحةً.",
        )
    import httpx

    from api.connectors import openmeteo

    try:
        daily = await openmeteo.fetch_daily_forecast(field_lat, field_lon, days=1)
        current = await openmeteo.fetch_current(field_lat, field_lon)
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        raise HTTPException(
            status_code=503,
            detail="تعذّر جلب الطقس من Open-Meteo — مرّر الطقس صراحةً.",
        ) from e
    if not daily or daily[0].solar_radiation_mj_m2 is None:
        raise HTTPException(
            status_code=503,
            detail="Open-Meteo لم يُرجِع إشعاعاً شمسيّاً لليوم — مرّر الطقس صراحةً.",
        )
    today = daily[0]
    return (
        WeatherDay(
            temp_max_c=today.temp_max_c,
            temp_min_c=today.temp_min_c,
            humidity_pct=current.humidity_pct,
            wind_speed_m_s=today.wind_max_ms,
            solar_radiation_mj_m2=today.solar_radiation_mj_m2,
            latitude_deg=field_lat,
            elevation_m=(req.elevation_m if req.elevation_m is not None else 0.0),
            day_of_year=(req.day_of_year or _today_doy()),
        ),
        "open-meteo",
    )


@router.post("/api/v1/fields/{field_id}/etc-dual")
async def field_etc_dual(
    req: EtcDualRequest,
    field_id: str = Path(..., description="معرّف الحقل"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """يحسب ETc المزدوج (FAO-56) للحقل: Kcb مرصود من NDVI الحيّ + طقس Open-Meteo (أو مُمرَّر).

    يقرأ الحقل (محصول/تاريخ زراعة/إحداثيّات) + أحدث NDVI/ملوحة (RLS)، يبني الطقس (مُمرَّر أو حيّ)،
    ويستدعي `compute_etc_dual`. صدق: NDVI/طقس مفقودان ⇒ تدرّج/503 معلَن؛ بطاقة/عمر ⇒ 422؛ DB ⇒ 503.
    """
    if api_main._DB_POOL is None:
        raise HTTPException(status_code=503, detail="القاعدة غير مفعّلة (DATABASE_URL)")
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            field_row = await conn.fetchrow(
                "SELECT crop, planting_date, lat, lon FROM fields WHERE field_id = $1", field_id
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

    # 3. NDVI الحيّ (جوهر الربط): تجاوز الطلب > COG طازج > المخزَّن > لا شيء (تدرّج صادق).
    #    الطازج يُجلب خدميّاً من raster-service (خارج اتّصال القاعدة) فقط إن لم يُمرَّر تجاوز
    #    و prefer_fresh_ndvi=True؛ أيّ تعذّر/real_data=false ⇒ تدرّج صامت للمخزَّن.
    stored_ndvi = freshness.get("ndvi_mean")
    ndvi_date = freshness.get("ndvi_date")
    fresh_ndvi = None
    if req.ndvi is None and req.prefer_fresh_ndvi:
        fresh_ndvi = await _fetch_fresh_ndvi(field_id)
    ndvi_used, ndvi_source = _pick_ndvi(req.ndvi, fresh_ndvi, stored_ndvi)
    if ndvi_source == "raster_fresh_cog":
        ndvi_date = date.today()  # COG طازج (date=latest) ⇒ تاريخه اليوم (لا تاريخ مخزَّن قديم)

    # 4. الملوحة (تجاوز الطلب > أحدث فحص تربة > 0)
    if req.soil_ece is not None:
        soil_ece, soil_ece_source = req.soil_ece, "request"
    elif freshness.get("soil_ec") is not None:
        soil_ece, soil_ece_source = float(freshness["soil_ec"]), "soil_lab_tests"
    else:
        soil_ece, soil_ece_source = 0.0, "default"

    # 5. الطقس (مُمرَّر أو حيّ من Open-Meteo) — خارج اتّصال القاعدة (لا حبس وصلة أثناء HTTP)
    field_lat = field_row["lat"] if field_row else None
    field_lon = field_row["lon"] if field_row else None
    weather, weather_source = await _resolve_weather(req, field_lat, field_lon)

    # 6. ET0 من **منتج محرّك الطقس** (المصدر الوحيد؛ لا نواة محلّيّة) بطقس اللقطة. تعذّر
    #    المحرّك ⇒ 503 fail-closed (لا حساب ET0 محلّيّ بديل). WS-C.1b Zero-Legacy.
    try:
        et0_prod = await get_et0_product(
            t_max_c=weather.temp_max_c,
            t_min_c=weather.temp_min_c,
            solar_rad_mj_m2=weather.solar_radiation_mj_m2,
            rh_mean_pct=weather.humidity_pct,
            wind_2m_ms=weather.wind_speed_m_s,
            lat_deg=weather.latitude_deg,
            elevation_m=weather.elevation_m,
            day_of_year=weather.day_of_year,
            tenant_id=getattr(user, "tenant_id", None),
        )
    except HTTPException as exc:
        if exc.status_code in (502, 503, 504):
            raise HTTPException(
                status_code=503,
                detail="weather-engine ET0 unavailable — fail-closed (no local ET0 fallback)",
            ) from exc
        raise
    et0_mm = et0_prod.get("et0_mm")
    if et0_mm is None:
        raise HTTPException(
            status_code=503,
            detail="weather-engine returned no ET0 — fail-closed (no local ET0 fallback)",
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
            et0_override=float(et0_mm),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"تعذّر حساب ETc المزدوج: {e}") from e

    if ndvi_used is None:
        result.assumptions.append("NDVI غير متاح للحقل ⇒ Kcb من العمر (تدرّج صادق، لا اختلاق)")

    payload = asdict(result)
    payload["field_id"] = field_id
    payload["weather_source"] = weather_source
    # نَسَب ET0 من منتج محرّك الطقس المرجعيّ (المصدر الوحيد) — يُعرَض في مخرَج etc-dual.
    payload["et0"] = {
        "et0_mm": et0_prod.get("et0_mm"),
        "method": et0_prod.get("method"),
        "quality_status": et0_prod.get("quality_status"),
        "formula_version": et0_prod.get("formula_version"),
        "valid_time": et0_prod.get("valid_time"),
        "weather_snapshot_id": et0_prod.get("weather_snapshot_id"),
        "source": "weather-engine",
    }
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
