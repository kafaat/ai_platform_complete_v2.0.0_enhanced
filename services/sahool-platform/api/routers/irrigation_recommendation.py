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

import logging

from fastapi import APIRouter, Depends, HTTPException
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
from api.weather_service_client import get_et0_product

router = APIRouter()

_LOG = logging.getLogger("sahool.irrigation.et0")

# رموز حالة المحرّك المتعذّر ⇒ فشل مُغلَق (لا حساب ET0 محلّيّ بديل).
_ENGINE_DOWN_CODES = (502, 503, 504)


async def _engine_et0(
    *,
    t_min_c: float,
    t_max_c: float,
    solar_rad_mj_m2: float | None,
    rh_mean_pct: float | None,
    wind_2m_ms: float | None,
    day_of_year: int,
    latitude_deg: float,
    elevation_m: float,
    valid_time: str | None = None,
    tenant_id: str | None = None,
) -> dict:
    """ET0 من محرّك الطقس — **مصدر ET0 الوحيد**. تعذّره ⇒ HTTPException (لا محلّيّ).

    نقطة وصل قابلة للـmonkeypatch في الاختبار (تُثبِت أنّ المسار يستهلك المحرّك فعلاً).
    """
    return await get_et0_product(
        t_max_c=t_max_c,
        t_min_c=t_min_c,
        solar_rad_mj_m2=solar_rad_mj_m2,
        rh_mean_pct=rh_mean_pct,
        wind_2m_ms=wind_2m_ms,
        lat_deg=latitude_deg,
        elevation_m=elevation_m,
        day_of_year=day_of_year,
        valid_time=valid_time,
        tenant_id=tenant_id,
    )


def _shadow_et0_diff(engine_et0_mm: float | None, w: WeatherInput) -> dict | None:
    """مقارنة ظلّيّة مؤقّتة: الإرث المحلّيّ (allowlisted) يُحسب للمقارنة فقط — **لا يدخل
    القرار قطّ**. الفرق ≈ 0 يُثبِت أنّ المحرّك يُعيد إنتاج الصيغة بأمانة قبل حذف الإرث.
    تُحذَف هذه الدالّة عند retire الإرث (C.1b النهائيّة).
    """
    try:
        legacy_mm, legacy_method = compute_et0(w)
    except Exception:  # noqa: BLE001 — الظلّ لا يجب أن يُعطّل المسار الحقيقيّ أبداً
        return None
    if engine_et0_mm is None or legacy_mm is None:
        return {"legacy_et0_mm": legacy_mm, "legacy_method": legacy_method, "diff_mm": None}
    diff = round(float(engine_et0_mm) - float(legacy_mm), 3)
    return {
        "legacy_et0_mm": round(float(legacy_mm), 3),
        "legacy_method": legacy_method,
        "diff_mm": diff,
        "diff_pct": round(100.0 * diff / legacy_mm, 1) if legacy_mm else None,
    }


def _et0_provenance(prod: dict, shadow: dict | None) -> dict:
    """كتلة نَسَب ET0 للمخرَج — المصدر والعقد والمقارنة الظلّيّة المؤقّتة."""
    block = {
        "et0_mm": prod.get("et0_mm"),
        "method": prod.get("method"),
        "quality_status": prod.get("quality_status"),
        "formula_version": prod.get("formula_version"),
        "valid_time": prod.get("valid_time"),
        "weather_snapshot_id": prod.get("weather_snapshot_id"),
        "source": "weather-engine",
    }
    if shadow is not None:
        block["shadow"] = shadow  # مؤقّت — يُحذَف مع الإرث
    return block


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
async def irrigation_recommendation(
    req: IrrigationRecommendationRequest,
    user: UserSchema = Depends(get_current_user),
):
    """توصية ريّ موحَّدة: صافٍ دائماً + إجهاد ملوحة عند توفّر EC + غسل مشروط.

    يُرجِع: ``net_irrigation_mm``/``salinity_leaching_mm``/``gross_irrigation_mm`` +
    ``policy`` (net_only/salinity_adjusted/salinity_with_leaching/blocked_for_review) +
    ``requires_expert_review`` + ``salinity_ks`` + ``evidence`` + ``rationale_ar``.

    ET0 من محرّك الطقس (المصدر الوحيد)؛ تعذّره ⇒ 503 صريح (لا حساب محلّيّ بديل).
    """
    try:
        et0_prod = await _engine_et0(
            t_min_c=req.t_min_c,
            t_max_c=req.t_max_c,
            solar_rad_mj_m2=req.solar_rad_mj_m2,
            rh_mean_pct=req.rh_mean_pct,
            wind_2m_ms=req.wind_2m_ms,
            day_of_year=req.day_of_year,
            latitude_deg=req.latitude_deg,
            elevation_m=req.elevation_m,
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503,
                detail="weather-engine ET0 unavailable — fail-closed (no local ET0 fallback)",
            ) from exc
        raise
    et0_mm = et0_prod.get("et0_mm")
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
        field_lat, _lon, crop, stage, _days = await _field_weather_context(conn, field_id)
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

    # ET0 من محرّك الطقس (المصدر الوحيد). خطّ العرض الحقيقيّ للحقل؛ الارتفاع افتراض
    # الهضبة اليمنيّة (2000م) حتّى إثراء التربة/الحقل (WS-D.2b/c). elevation مطابق للإرث
    # ليكون فرق الظلّ ≈ 0 (إثبات أمانة إعادة الإنتاج).
    _elev_default_m = 2000.0
    try:
        et0_prod = await _engine_et0(
            t_min_c=req.t_min_c,
            t_max_c=req.t_max_c,
            solar_rad_mj_m2=req.solar_rad_mj_m2,
            rh_mean_pct=req.rh_mean_pct,
            wind_2m_ms=req.wind_2m_ms,
            day_of_year=req.day_of_year,
            latitude_deg=field_lat,
            elevation_m=_elev_default_m,
        )
    except HTTPException as exc:
        # فشل مُغلَق: تعذّر المحرّك ⇒ لا حساب ET0 محلّيّ بديل (dependency_unavailable).
        if exc.status_code in _ENGINE_DOWN_CODES:
            return {
                "status": "dependency_unavailable",
                "field_id": field_id,
                "season_id": season_id,
                "inputs": inputs,
                "recommendation": None,
                "ownership": "recommendation_candidate → decision-service",
                "confidence": None,
                "evidence_ids": evidence_ids,
                "limitations": [
                    *state["limitations"],
                    "weather-engine ET0 unavailable — fail-closed (no local ET0 fallback)",
                ],
                "calibrated": False,
            }
        raise

    et0_mm = et0_prod.get("et0_mm")
    # مقارنة ظلّيّة مؤقّتة (الإرث لا يدخل القرار) — نفس مدخلات المحرّك ⇒ فرق ≈ 0.
    shadow = _shadow_et0_diff(
        et0_mm,
        WeatherInput(
            t_min_c=req.t_min_c,
            t_max_c=req.t_max_c,
            solar_rad_mj_m2=req.solar_rad_mj_m2,
            rh_mean_pct=req.rh_mean_pct,
            wind_2m_ms=req.wind_2m_ms,
            latitude_deg=field_lat,
            elevation_m=_elev_default_m,
            day_of_year=req.day_of_year,
        ),
    )
    if shadow and shadow.get("diff_mm") is not None:
        _LOG.info(
            "et0_shadow_diff field=%s snapshot=%s engine_mm=%s legacy_mm=%s diff_mm=%s",
            field_id,
            et0_prod.get("weather_snapshot_id"),
            et0_mm,
            shadow["legacy_et0_mm"],
            shadow["diff_mm"],
        )
    evidence_ids.append(f"weather-engine-et0:{et0_prod.get('weather_snapshot_id')}")

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
        "et0": _et0_provenance(et0_prod, shadow),
        "ownership": "recommendation_candidate → decision-service",
        "confidence": confidence,
        "evidence_ids": evidence_ids,
        "limitations": state["limitations"],
        "calibrated": False,
    }
