"""api/routers/water_balance.py — ميزان الماء ET0 (FAO-56 Water Balance)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الدوالّ النقيّة (``api.water_balance``) تُستورَد مباشرةً من وحدتها — وهي نفس الكائنات
التي كانت في ``main`` (لا تُبقى استيراداً يتيماً هناك). أمّا التبعيات/النماذج
المُعرَّفة في ``main`` فتبقى هناك وتُستورَد من ``api.main`` حفظاً
لـ``_rebuild_pydantic_models`` واستيرادات الاختبارات. لتفادي الاستيراد الدائريّ:
``api.main`` يستورد هذا الموجِّه في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    UserSchema,
    get_current_user,
)
from api.water_balance import WeatherInput, water_balance, water_balance_auto
from api.water_balance_models import WaterBalanceRequest
from api.weather_service_client import get_et0_product

router = APIRouter()

# رموز تعذّر المحرّك ⇒ فشل مُغلَق (لا حساب ET0 محلّيّ بديل).
_ENGINE_DOWN_CODES = (502, 503, 504)


async def _engine_et0_from_request(req: WaterBalanceRequest) -> tuple[float, str]:
    """يجلب ET0 المرجعيّ من منتج محرّك الطقس (المصدر الوحيد) لمدخلات الطلب.

    تعذّر المحرّك/نقص ⇒ HTTPException(503) fail-closed (لا نواة ET0 محلّيّة).
    """
    try:
        prod = await get_et0_product(
            t_max_c=req.t_max_c,
            t_min_c=req.t_min_c,
            solar_rad_mj_m2=req.solar_rad_mj_m2,
            rh_mean_pct=req.rh_mean_pct,
            wind_2m_ms=req.wind_2m_ms,
            lat_deg=req.latitude_deg,
            elevation_m=req.elevation_m,
            day_of_year=req.day_of_year,
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503,
                detail="weather-engine ET0 unavailable — fail-closed (no local ET0 fallback)",
            ) from exc
        raise
    et0_mm = prod.get("et0_mm")
    if et0_mm is None:
        raise HTTPException(
            status_code=503,
            detail="weather-engine returned no ET0 — fail-closed (no local ET0 fallback)",
        )
    return float(et0_mm), str(prod.get("method") or "weather-engine")


@router.post("/api/v1/water-balance")
async def compute_water_balance(
    req: WaterBalanceRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يحسب توصية الريّ (ET0 → ETc → احتياج صافٍ بعد المطر).

    ET0 من **محرّك الطقس** (المصدر الوحيد؛ لا نواة محلّيّة) — تعذّره ⇒ 503 صريح.
    الملوحة **مُطفأة افتراضيّاً**؛ تُفعَّل **تلقائيّاً** فقط عند تمرير تحليل ملوحة مخبريّ
    (``soil_ece``/``water_ecw`` + العمر + الثقة) — يقرّرها ``salinity_policy`` بصدق، ويُعرَض
    القرار في ``salinity_decision``. غياب التحليل ⇒ شكل الردّ كما كان تماماً (سلوك محفوظ).
    """
    et0_mm, et0_method = await _engine_et0_from_request(req)
    w = WeatherInput(
        t_min_c=req.t_min_c,
        t_max_c=req.t_max_c,
        solar_rad_mj_m2=req.solar_rad_mj_m2,
        rh_mean_pct=req.rh_mean_pct,
        wind_2m_ms=req.wind_2m_ms,
        latitude_deg=req.latitude_deg,
        elevation_m=req.elevation_m,
        day_of_year=req.day_of_year,
    )
    # تحليل ملوحة مُمرَّر؟ ⇒ مسار التفعيل التلقائيّ (مع عرض القرار). وإلّا المسار القائم تماماً.
    has_salinity_analysis = (
        req.soil_ece is not None
        or req.water_ecw is not None
        or req.analysis_age_days is not None
        or req.analysis_confidence is not None
        or req.crop_sensitive
        or req.saline_region
    )
    if has_salinity_analysis:
        result, decision = water_balance_auto(
            w,
            req.crop,
            req.stage,
            rain_mm=req.rain_mm,
            ndvi=req.ndvi,
            forecast_rain_mm=req.forecast_rain_mm,
            forecast_window_days=req.forecast_window_days,
            forecast_confidence=req.forecast_confidence,
            forecast_infiltration=req.forecast_infiltration,
            soil_ece=req.soil_ece,
            water_ecw=req.water_ecw,
            analysis_age_days=req.analysis_age_days,
            confidence=req.analysis_confidence,
            crop_sensitive=req.crop_sensitive,
            saline_region=req.saline_region,
            et0_mm=et0_mm,
            et0_method=et0_method,
        )
        out = result.to_dict()
        out["salinity_decision"] = decision.to_dict()
        return out
    return water_balance(
        w,
        req.crop,
        req.stage,
        rain_mm=req.rain_mm,
        ndvi=req.ndvi,
        forecast_rain_mm=req.forecast_rain_mm,
        forecast_window_days=req.forecast_window_days,
        forecast_confidence=req.forecast_confidence,
        forecast_infiltration=req.forecast_infiltration,
        et0_mm=et0_mm,
        et0_method=et0_method,
    ).to_dict()
