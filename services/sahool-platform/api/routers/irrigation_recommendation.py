"""api/routers/irrigation_recommendation.py — توصية ريّ موحَّدة مشروطة بالملوحة (H5)
================================================================================
نقطة جديدة ``POST /api/v1/irrigation-recommendation`` تكشف سياسة
``api.irrigation_recommendation_policy.recommend_irrigation`` — تختار صيغة الريّ
بحسب توفّر فحص EC المخبريّ (Ks دائماً عند توفّره + غسل مشروط)، وتتدهور بصدق.

لا تكسر ``/api/v1/water-balance`` (تبقى كما هي). تُحسب ET0 بنفس مسار FAO-56 المُعاد
استخدامه (``api.water_balance.compute_et0``) ضماناً لتطابق الأساس.

**صدق:** مدخلات الملوحة (ECe/ECw/الصرف/الكفاءة) تُمرَّر صراحةً في الطلب — لا تُختلق.
إثراؤها من حالة الحقل (soil_lab_tests) متابعةٌ لاحقة موثَّقة. القيم تحتاج معايرة ميدانيّة.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.irrigation_recommendation_policy import recommend_irrigation
from api.main import UserSchema, get_current_user
from api.water_balance import WeatherInput, compute_et0

router = APIRouter()


class IrrigationRecommendationRequest(BaseModel):
    crop: str | None = None
    stage: str = "mid"  # initial|development|mid|late
    t_min_c: float
    t_max_c: float
    rain_recent_mm: float = 0.0
    forecast_rain_mm: float = 0.0
    soil_moisture_pct: float | None = None
    kc_override: float | None = None  # Kc دقيق من الفينولوجيا إن توفّر
    # طقس Penman-Monteith (اختياريّ — يسقط إلى Hargreaves عند الغياب)
    solar_rad_mj_m2: float | None = None
    rh_mean_pct: float | None = None
    wind_2m_ms: float | None = None
    latitude_deg: float = 15.5
    elevation_m: float = 2000.0
    day_of_year: int = 100
    # ── مدخلات الملوحة (فحص مخبريّ) ──
    soil_ece: float | None = None  # ECe من soil_lab_tests
    soil_ec_age_days: int | None = None  # عُمر الفحص (للموثوقيّة)
    crop_salt_tolerance_ece: float | None = None  # عتبة المحصول (FAO-56 T23)
    salt_slope_pct: float | None = None
    # ── مدخلات الغسل (مشروطة) ──
    water_ec: float | None = None  # ECw ماء الريّ
    drainage: str | None = None  # fast|medium|slow
    irrigation_efficiency: float | None = None


@router.post("/api/v1/irrigation-recommendation")
def irrigation_recommendation(
    req: IrrigationRecommendationRequest,
    user: UserSchema = Depends(get_current_user),
):
    """توصية ريّ موحَّدة: صافٍ دائماً + إجهاد ملوحة عند توفّر EC + غسل مشروط.

    يُرجِع: ``net_irrigation_mm``/``salinity_leaching_mm``/``gross_irrigation_mm`` +
    ``policy`` (net_only/salinity_adjusted/salinity_with_leaching/blocked_for_review) +
    ``requires_expert_review`` + ``salinity_ks`` + ``evidence`` + ``rationale_ar``.
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
    et0_mm, _method = compute_et0(w)
    return recommend_irrigation(
        et0_mm=et0_mm,
        crop=req.crop,
        stage=req.stage,
        rain_recent_mm=req.rain_recent_mm,
        forecast_rain_mm=req.forecast_rain_mm,
        soil_moisture_pct=req.soil_moisture_pct,
        kc_override=req.kc_override,
        soil_ece=req.soil_ece,
        soil_ec_age_days=req.soil_ec_age_days,
        crop_salt_tolerance_ece=req.crop_salt_tolerance_ece,
        salt_slope_pct=req.salt_slope_pct,
        water_ec=req.water_ec,
        drainage=req.drainage,
        irrigation_efficiency=req.irrigation_efficiency,
    )
