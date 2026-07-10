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

from api.canonical_water_stress import canonical_water_stress
from api.field_context import _field_weather_context
from api.irrigation_recommendation_policy import recommend_irrigation
from api.irrigation_state_guard import assess_irrigation_state
from api.main import (
    Permission,
    UserSchema,
    get_current_user,
    require_permission,
    tenant_connection,
)
from api.soil_water import soil_water_params
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
    # ── مدخلات الإجهاد المائيّ (استنزاف منطقة الجذور) — تقود قرار الإطلاق ──
    depletion_mm: float | None = None  # Dr من water_ledger عبر الحالة الكنسيّة
    taw_mm: float | None = None  # TAW من soil_water_params
    raw_fraction: float = 0.5  # p (FAO-56)
    water_stress_class: str | None = None  # normal|watch|critical (canonical)
    policy: str | None = None  # water_saving|yield_max|profit_max|sustainability|risk_averse
    water_price_per_m3: float | None = None  # لـ profit_max
    yield_value_per_ha: float | None = None  # لـ profit_max


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
        depletion_mm=req.depletion_mm,
        taw_mm=req.taw_mm,
        raw_fraction=req.raw_fraction,
        water_stress_class=req.water_stress_class,
        policy=req.policy,
        water_price_per_m3=req.water_price_per_m3,
        yield_value_per_ha=req.yield_value_per_ha,
    )


class FieldIrrigationRequest(BaseModel):
    """طقس Penman-Monteith فقط — الاستنزاف/TAW/الإجهاد تُقرأ آليّاً من حالة الحقل."""

    t_min_c: float
    t_max_c: float
    solar_rad_mj_m2: float | None = None
    rh_mean_pct: float | None = None
    wind_2m_ms: float | None = None
    day_of_year: int = 100
    root_depth_m: float | None = None  # عمق الجذور (لاشتقاق TAW)؛ None ⇒ افتراضيّ موسوم
    policy: str | None = None  # سياسة الريّ (water_saving افتراضاً)
    water_price_per_m3: float | None = None
    yield_value_per_ha: float | None = None


@router.post("/api/v1/fields/{field_id}/irrigation-recommendation")
async def field_irrigation_recommendation(
    field_id: str,
    req: FieldIrrigationRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """توصية ريّ مُثراة تلقائيّاً من حالة الحقل (WS-D.2) — **مرشَّح** لخدمة القرار.

    يقرأ آليّاً (لا يطلب من العميل): استنزاف منطقة الجذور Dr + ثقته من ``water_ledger``،
    وTAW من ``soil_water_params`` (مع إعلان مصدره)، والمحصول/المرحلة من الموسم النشط،
    والإجهاد المائيّ الكنسيّ. **صدق:** مفقود ≠ صفر · ``0 ≤ Dr ≤ TAW`` وإلّا
    ``inconsistent_state`` بلا قصّ · دفتر قديم ⇒ قيد مُعلَن · TAW غير المُعايَر مُعلَن.

    **حدود الملكيّة:** هذه توصية **مرشَّحة** (candidate) — لا تُنشئ مهمّة؛ التنفيذ عبر
    خدمة القرار (موافقة/سياسة). ET0 من طقس الطلب (FAO-56)؛ الاستنزاف يقود قرار الإطلاق.
    """
    from datetime import date

    async with tenant_connection(user) as conn:
        # سياق الحقل + الموسم النشط (يرفع 404 إن غاب الحقل).
        _lat, _lon, crop, stage, _days = await _field_weather_context(conn, field_id)
        season = await conn.fetchrow(
            "SELECT season_id FROM seasons WHERE field_id = $1 AND status = 'active' "
            "ORDER BY created_at DESC LIMIT 1",
            field_id,
        )
        season_id = season["season_id"] if season else None
        # أحدث استنزاف + عمره (نضارة) — مفقود يبقى None (لا صفر مُختلَق).
        lrow = await conn.fetchrow(
            "SELECT depletion_mm, confidence, soil_moisture_pct, ledger_date, "
            "EXTRACT(EPOCH FROM (now() - updated_at)) / 3600.0 AS age_hours "
            "FROM water_ledger WHERE field_id = $1 ORDER BY ledger_date DESC LIMIT 1",
            field_id,
        )

    depletion_mm = lrow["depletion_mm"] if lrow else None
    dep_conf = lrow["confidence"] if lrow else None
    ledger_date = lrow["ledger_date"] if lrow else None
    ledger_age_hours = (
        float(lrow["age_hours"]) if (lrow and lrow["age_hours"] is not None) else None
    )

    # TAW من بارامترات التربة (النسيج غير مقروء بعد ⇒ احتياطيّ موسوم صدقاً).
    sw = soil_water_params(texture=None, root_depth_m=req.root_depth_m)
    taw_mm = sw["taw_mm"]
    taw_source = "soil_lab" if sw.get("texture_known") else "texture_fallback"

    state = assess_irrigation_state(
        depletion_mm=depletion_mm,
        taw_mm=taw_mm,
        ledger_age_hours=ledger_age_hours,
        taw_source=taw_source,
    )

    inputs = {
        "depletion_mm": round(float(depletion_mm), 2) if depletion_mm is not None else None,
        "taw_mm": taw_mm,
        "raw_fraction": sw["raw_fraction"],
        "depletion_fraction": state["depletion_fraction"],
        "taw_source": taw_source,
        "ledger_age_hours": round(ledger_age_hours, 1) if ledger_age_hours is not None else None,
        "crop": crop,
        "stage": stage,
    }
    evidence_ids = [f"field-context:{field_id}", f"soil-water-params:{taw_source}"]
    if ledger_date is not None:
        evidence_ids.append(f"water-ledger:{field_id}:{ledger_date}")

    # fail-closed: حالة غير متّسقة/ناقصة ⇒ لا توصية (لا قصّ، لا افتراض صفر).
    if not state["available"]:
        return {
            "status": state["status"],
            "field_id": field_id,
            "season_id": season_id,
            "inputs": inputs,
            "recommendation": None,
            "ownership": "recommendation_candidate → decision-service",
            "confidence": None,
            "evidence_ids": evidence_ids,
            "limitations": state["limitations"],
            "calibrated": False,
        }

    # الإجهاد المائيّ الكنسيّ (للطبقة/الإلحاح) — best-effort، لا يحجب.
    stress = canonical_water_stress(
        {"depletion_mm": depletion_mm, "taw_mm": taw_mm, "raw_fraction": sw["raw_fraction"]}
    )
    water_stress_class = stress["water_stress_class"] if stress else None

    et0_mm, _method = compute_et0(
        WeatherInput(
            t_min_c=req.t_min_c,
            t_max_c=req.t_max_c,
            solar_rad_mj_m2=req.solar_rad_mj_m2,
            rh_mean_pct=req.rh_mean_pct,
            wind_2m_ms=req.wind_2m_ms,
            day_of_year=req.day_of_year,
        )
    )
    rec = recommend_irrigation(
        et0_mm=et0_mm,
        crop=crop,
        stage=stage,
        depletion_mm=depletion_mm,
        taw_mm=taw_mm,
        raw_fraction=sw["raw_fraction"],
        water_stress_class=water_stress_class,
        policy=req.policy,
        water_price_per_m3=req.water_price_per_m3,
        yield_value_per_ha=req.yield_value_per_ha,
    )

    # ثقة: تبدأ من ثقة الاستنزاف المخزَّنة، وتُخفَّض بكلّ قيد مُعلَن (شفّاف، غير معايَر).
    base_conf = float(dep_conf) if dep_conf is not None else 0.5
    confidence = round(max(0.0, base_conf - 0.15 * len(state["limitations"])), 2)

    return {
        "status": "recommendation_ready",
        "field_id": field_id,
        "season_id": season_id,
        "generated_on": date.today().isoformat(),
        "inputs": inputs,
        "recommendation": {
            "should_irrigate": rec["should_irrigate"],
            "trigger_reason": rec["trigger_reason"],
            "net_irrigation_mm": rec["net_irrigation_mm"],
            "target_refill_mm": rec["target_refill_mm"],
            "water_stress_class": water_stress_class,
            "urgency": rec["urgency"],
            "policy_knobs": rec["policy_knobs"],
        },
        "ownership": "recommendation_candidate → decision-service",
        "confidence": confidence,
        "evidence_ids": evidence_ids,
        "limitations": state["limitations"],
        "calibrated": False,
    }
