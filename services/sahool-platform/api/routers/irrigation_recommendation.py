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
from api.decision_service_client import record_decision
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
from api.soil_enrichment import extract_texture, soil_water_provenance
from api.soil_water import soil_water_params
from api.water_balance import WeatherInput, compute_et0
from api.weather_service_client import get_et0_product, get_weather_forecast

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


async def _field_weather_snapshot(latitude_deg: float, longitude_deg: float) -> dict:
    """لقطة طقس اليوم من محرّك الطقس (المصدر الوحيد) — المسار الأساسيّ لـD.2c.

    يجلب توقّع اليوم لموقع الحقل ويشتقّ day-of-year من ``valid_time``. تعذّر المحرّك
    أو غياب أيّام ⇒ HTTPException (fail-closed؛ لا توصية على طقس مفقود). RH غير متوفّر
    في التوقّع اليوميّ (ساعيّ فقط) ⇒ None (ET0 يسقط لـHargreaves صراحةً). نقطة وصل
    قابلة للـmonkeypatch.
    """
    from datetime import date as _date

    fc = await get_weather_forecast(latitude_deg, longitude_deg, days=1)
    days = fc.get("days") or []
    if not days:
        raise HTTPException(
            status_code=503,
            detail="weather-engine forecast returned no days — fail-closed (no recommendation)",
        )
    d0 = days[0]
    valid_time = d0.get("date")
    try:
        doy = _date.fromisoformat(valid_time).timetuple().tm_yday if valid_time else None
    except (TypeError, ValueError):
        doy = None
    return {
        "t_min_c": d0.get("temp_min_c"),
        "t_max_c": d0.get("temp_max_c"),
        "wind_2m_ms": d0.get("wind_max_ms"),
        "solar_rad_mj_m2": d0.get("solar_radiation_mj_m2"),
        "rh_mean_pct": None,  # غير متوفّر في التوقّع اليوميّ
        "day_of_year": doy,
        "valid_time": valid_time,
        "source": "weather-engine-forecast",
    }


async def _submit_candidate_to_decision(payload: dict, tenant_id: str | None) -> dict:
    """يقدّم المرشَّح إلى خدمة القرار (تسجيل معلَّق للموافقة) — نقطة وصل قابلة للـmonkeypatch.

    **لا ينفّذ**: يُسجّل قراراً معلَّقاً (pending_approval) فقط؛ التنفيذ المحروس (حواجز +
    human-in-loop + طابور) يبقى في مسار decision_dispatch. تعذّر الخدمة ⇒ HTTPException.
    """
    return await record_decision(payload, tenant_id=tenant_id)


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
    """المسار الأساسيّ: الطقس يُجلَب آليّاً من محرّك الطقس (WS-D.2c). الحرارة اختياريّة
    كتجاوز يدويّ فقط — لا كمسار أساسيّ. الاستنزاف/TAW/التربة تُقرأ آليّاً من حالة الحقل."""

    # تجاوز يدويّ اختياريّ (ليس المسار الأساسيّ) — None ⇒ جلب تلقائيّ من المحرّك.
    t_min_c: float | None = None
    t_max_c: float | None = None
    solar_rad_mj_m2: float | None = None
    rh_mean_pct: float | None = None
    wind_2m_ms: float | None = None
    day_of_year: int | None = None
    root_depth_m: float | None = None  # عمق الجذور (لاشتقاق TAW)؛ None ⇒ افتراضيّ موسوم
    policy: str | None = None  # سياسة الريّ (water_saving افتراضاً)
    water_price_per_m3: float | None = None
    # WS-D.2d: تقديم صريح للمرشَّح إلى خدمة القرار (لا تلقائيّ — احترام حوكمة الموافقة).
    submit_to_decision: bool = False
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
        field_lat, field_lon, crop, stage, _days = await _field_weather_context(conn, field_id)
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
        # WS-D.2b: أحدث فحص تربة معتمَد ⇒ نسيج مقيس مخبريّاً (+ عمره) لتحسين TAW.
        # النسيج لا عمود مُصنَّف له اليوم (جرد المصادر) — من JSONB. غيابه ⇒ fallback عامّ.
        soil_row = await conn.fetchrow(
            "SELECT sampled_on, result, "
            "EXTRACT(EPOCH FROM (now() - sampled_on)) / 86400.0 AS age_days "
            "FROM soil_lab_tests "
            "WHERE field_id = $1 AND status IN ('approved', 'published') "
            "AND sampled_on IS NOT NULL ORDER BY sampled_on DESC LIMIT 1",
            field_id,
        )
        # WS-D.3: التأكيد الطيفيّ (NDMI+MSI) — يصل فعلاً إلى مرشَّح الريّ. قرار المستخدم:
        # كلا المؤشّرين مطلوبان بتوافق زمنيّ، وإلّا لا تصعيد. v99 قد لا تكون مطبّقة ⇒
        # تخطٍّ آمن (لا يحجب التوصية — التأكيد best-effort).
        spectral_row = None
        try:
            async with conn.transaction():  # SAVEPOINT — v99 غير مطبّقة ⇒ لا يُفسِد الاتّصال
                spectral_row = await conn.fetchrow(
                    "SELECT last_ndmi_mean, last_msi_mean, last_ndmi_date, last_msi_date "
                    "FROM imagery_automation_fields WHERE field_id = $1",
                    field_id,
                )
        except Exception:  # noqa: BLE001 — جدول الأتمتة غير مطبّق ⇒ لا تأكيد طيفيّ
            spectral_row = None

    depletion_mm = lrow["depletion_mm"] if lrow else None
    dep_conf = lrow["confidence"] if lrow else None
    ledger_date = lrow["ledger_date"] if lrow else None
    ledger_age_hours = (
        float(lrow["age_hours"]) if (lrow and lrow["age_hours"] is not None) else None
    )

    # WS-D.2b: نسيج مخبريّ حقيقيّ ⇒ TAW أدقّ + نَسَب مصدر صريح + خفض ثقة عند fallback.
    texture_lab = extract_texture(soil_row["result"]) if soil_row else None
    texture_sampled_on = str(soil_row["sampled_on"]) if soil_row else None
    texture_age_days = (
        float(soil_row["age_days"]) if (soil_row and soil_row["age_days"] is not None) else None
    )
    sw = soil_water_params(texture=texture_lab, root_depth_m=req.root_depth_m)
    taw_mm = sw["taw_mm"]
    soil_prov = soil_water_provenance(
        texture_known=bool(sw.get("texture_known")),
        texture_value=sw.get("texture"),
        texture_sampled_on=texture_sampled_on,
        texture_age_days=texture_age_days,
        root_depth_supplied=req.root_depth_m is not None and req.root_depth_m > 0,
    )
    taw_source = soil_prov["taw"]["source"]

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
        "soil_provenance": soil_prov,
        "ledger_age_hours": round(ledger_age_hours, 1) if ledger_age_hours is not None else None,
        "crop": crop,
        "stage": stage,
    }
    evidence_ids = [f"field-context:{field_id}", f"soil-water-params:{taw_source}"]
    if soil_prov["texture"]["source"] == "lab_measured" and texture_sampled_on is not None:
        evidence_ids.append(f"soil-lab-texture:{field_id}:{texture_sampled_on}")
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

    # الإجهاد المائيّ الكنسيّ (للطبقة/الإلحاح) — best-effort، لا يحجب. WS-D.3: يُمرَّر
    # التأكيد الطيفيّ (NDMI+MSI + تاريخاهما) فيصل MSI فعلاً إلى المرشَّح؛ التوافق الزمنيّ
    # وغياب أحد الدليلين يُقرّران التصعيد داخل canonical_water_stress (لا هنا).
    stress = canonical_water_stress(
        {
            "depletion_mm": depletion_mm,
            "taw_mm": taw_mm,
            "raw_fraction": sw["raw_fraction"],
            "ndmi": spectral_row["last_ndmi_mean"] if spectral_row else None,
            "msi": spectral_row["last_msi_mean"] if spectral_row else None,
            "ndmi_date": spectral_row["last_ndmi_date"] if spectral_row else None,
            "msi_date": spectral_row["last_msi_date"] if spectral_row else None,
        }
    )
    water_stress_class = stress["water_stress_class"] if stress else None
    # WS-D.3: نَسَب التأكيد الطيفيّ في الأدلّة (يُثبِت أنّ MSI وصل المرشَّح).
    if stress and stress.get("spectral_confirmation_available"):
        evidence_ids.append(
            f"spectral-confirmation:ndmi+msi:{'detected' if stress.get('spectral_stress_detected') else 'no-stress'}"
        )

    _elev_default_m = 2000.0

    # WS-D.2c: الطقس يُجلَب آليّاً من محرّك الطقس (المسار الأساسيّ). حرارة الطلب تجاوز
    # يدويّ فقط. تعذّر جلب الطقس ⇒ dependency_unavailable (لا توصية على طقس مفقود).
    manual_weather = req.t_min_c is not None and req.t_max_c is not None
    weather_limitation: str | None = None
    try:
        if manual_weather:
            wx = {
                "t_min_c": req.t_min_c,
                "t_max_c": req.t_max_c,
                "solar_rad_mj_m2": req.solar_rad_mj_m2,
                "rh_mean_pct": req.rh_mean_pct,
                "wind_2m_ms": req.wind_2m_ms,
                "day_of_year": req.day_of_year if req.day_of_year is not None else 100,
                "valid_time": None,
                "source": "manual_override",
            }
            weather_limitation = "manual weather override (not auto-fetched from weather-engine)"
        else:
            wx = await _field_weather_snapshot(field_lat, field_lon)
    except HTTPException as exc:
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
                    "weather-engine forecast unavailable — fail-closed (no recommendation)",
                ],
                "calibrated": False,
            }
        raise

    # طقس ناقص (لا حرارة) ⇒ لا توصية (لا اختلاق).
    if wx.get("t_min_c") is None or wx.get("t_max_c") is None:
        return {
            "status": "dependency_unavailable",
            "field_id": field_id,
            "season_id": season_id,
            "inputs": inputs,
            "recommendation": None,
            "ownership": "recommendation_candidate → decision-service",
            "confidence": None,
            "evidence_ids": evidence_ids,
            "limitations": [*state["limitations"], "weather snapshot missing temperature"],
            "calibrated": False,
        }

    # ET0 من محرّك الطقس (المصدر الوحيد) بلقطة الحقل. الارتفاع افتراض الهضبة (2000م).
    try:
        et0_prod = await _engine_et0(
            t_min_c=wx["t_min_c"],
            t_max_c=wx["t_max_c"],
            solar_rad_mj_m2=wx.get("solar_rad_mj_m2"),
            rh_mean_pct=wx.get("rh_mean_pct"),
            wind_2m_ms=wx.get("wind_2m_ms"),
            day_of_year=wx.get("day_of_year") or 100,
            latitude_deg=field_lat,
            elevation_m=_elev_default_m,
            valid_time=wx.get("valid_time"),
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
            t_min_c=wx["t_min_c"],
            t_max_c=wx["t_max_c"],
            solar_rad_mj_m2=wx.get("solar_rad_mj_m2"),
            rh_mean_pct=wx.get("rh_mean_pct"),
            wind_2m_ms=wx.get("wind_2m_ms"),
            latitude_deg=field_lat,
            elevation_m=_elev_default_m,
            day_of_year=wx.get("day_of_year") or 100,
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

    # ثقة: تبدأ من ثقة الاستنزاف المخزَّنة، وتُخفَّض بكلّ قيد مُعلَن (حالة + تربة)
    # وبعقوبة نَسَب التربة (fallback عامّ) — شفّاف، غير معايَر (WS-D.2b).
    base_conf = float(dep_conf) if dep_conf is not None else 0.5
    confidence = round(
        max(
            0.0,
            base_conf - 0.15 * len(state["limitations"]) - soil_prov["confidence_penalty"],
        ),
        2,
    )

    # WS-D.2d: المرشَّح ليس قراراً. approval_state يمنع عرض «اروِ» كقرار نهائيّ قبل
    # الاعتماد. التقديم صريح فقط (submit_to_decision) — لا تلقائيّ (حوكمة الموافقة).
    approval_state = "not_submitted"
    decision_id = None
    submit_limitation: str | None = None
    if req.submit_to_decision:
        candidate_payload = {
            "decision_type": "irrigation",
            "field_id": field_id,
            "season_id": season_id,
            "recommendation": {
                "should_irrigate": rec["should_irrigate"],
                "trigger_reason": rec["trigger_reason"],
                "net_irrigation_mm": rec["net_irrigation_mm"],
                "target_refill_mm": rec["target_refill_mm"],
                "urgency": rec["urgency"],
            },
            "confidence": confidence,
            "evidence_ids": evidence_ids,
            "provenance": {
                "et0": et0_prod.get("weather_snapshot_id"),
                "weather": wx.get("valid_time"),
                "taw_source": taw_source,
            },
            "status": "pending_approval",
            "calibrated": False,
        }
        try:
            res = await _submit_candidate_to_decision(
                candidate_payload, getattr(user, "tenant_id", None)
            )
            decision_id = res.get("decision_id") or res.get("id")
            approval_state = "pending_approval"
        except HTTPException as exc:
            # فشل مُغلَق: تعذّر خدمة القرار ⇒ لم يُقدَّم (لا اختلاق تقديم ناجح).
            if exc.status_code in _ENGINE_DOWN_CODES:
                approval_state = "submit_unavailable"
                submit_limitation = "decision-service unavailable — candidate not submitted"
            else:
                raise

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
        "weather": {
            "source": wx["source"],
            "valid_time": wx.get("valid_time"),
            "day_of_year": wx.get("day_of_year"),
        },
        # WS-D.3: تأكيد طيفيّ (NDMI+MSI) — يُثبِت أنّ MSI وصل المرشَّح؛ غياب أحد الدليلين
        # أو تباعد تاريخيهما ⇒ available=False و detected=None (لا تصعيد مُختلَق).
        "spectral_confirmation": {
            "available": bool(stress and stress.get("spectral_confirmation_available")),
            "stress_detected": stress.get("spectral_stress_detected") if stress else None,
            "confidence": stress.get("spectral_confidence") if stress else None,
            "escalation_eligible": bool(stress and stress.get("escalation_eligible")),
        },
        "ownership": "recommendation_candidate → decision-service",
        # WS-D.2d: حالة الاعتماد صريحة — «اروِ» ليس قراراً نهائيّاً قبل approved.
        "approval_state": approval_state,
        "decision_id": decision_id,
        "confidence": confidence,
        "evidence_ids": evidence_ids,
        "limitations": [
            *state["limitations"],
            *soil_prov["limitations"],
            *([weather_limitation] if weather_limitation else []),
            *([submit_limitation] if submit_limitation else []),
        ],
        "calibrated": False,
    }
