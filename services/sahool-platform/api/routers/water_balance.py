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

from fastapi import APIRouter, Depends

from api.main import (
    UserSchema,
    get_current_user,
)
from api.water_balance import WeatherInput, water_balance, water_balance_auto
from api.water_balance_models import WaterBalanceRequest

router = APIRouter()


@router.post("/api/v1/water-balance")
def compute_water_balance(
    req: WaterBalanceRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يحسب توصية الريّ (ET0 → ETc → احتياج صافٍ بعد المطر).

    الملوحة **مُطفأة افتراضيّاً**؛ تُفعَّل **تلقائيّاً** فقط عند تمرير تحليل ملوحة مخبريّ
    (``soil_ece``/``water_ecw`` + العمر + الثقة) — يقرّرها ``salinity_policy`` بصدق، ويُعرَض
    القرار في ``salinity_decision``. غياب التحليل ⇒ الردّ كما كان تماماً (سلوك محفوظ).
    """
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
    ).to_dict()
