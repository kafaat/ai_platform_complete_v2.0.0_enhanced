"""api/routers/irrigation_recommendation.py — توصية ريّ موحَّدة مشروطة بالملوحة (H5)
================================================================================
نقطة جديدة ``POST /api/v1/irrigation-recommendation`` تكشف سياسة
``api.irrigation_recommendation_policy.recommend_irrigation`` — تختار صيغة الريّ
بحسب توفّر فحص EC المخبريّ (Ks دائماً عند توفّره + غسل مشروط)، وتتدهور بصدق.

ET0 يُجلَب من **منتج محرّك الطقس** (``get_et0_product``) — المصدر الوحيد للمنصّة؛
تعذّره ⇒ 503 fail-closed (لا نواة ET0 محلّيّة، WS-C.1b Zero-Legacy).

**صدق:** مدخلات الملوحة (ECe/ECw/الصرف/الكفاءة) تُمرَّر صراحةً في الطلب — لا تُختلق.
إثراؤها من حالة الحقل (soil_lab_tests) متابعةٌ لاحقة موثَّقة. القيم تحتاج معايرة ميدانيّة.
"""

from __future__ import annotations

import hashlib
import json
import logging

from fastapi import APIRouter, Depends, HTTPException

from api.canonical_water_stress import canonical_water_stress

# مرحلةُ المرشَّح تُستورَد ولا تُكرَّر: سلسلةٌ ثانيةٌ باسم `"candidate"` هنا كانت ستُطابِق
# اليوم وتنحرف غداً، وشرطُ الإثبات يقارنها بما يُعيده المُسجِّل.
from api.crop_decision_bridge import CANDIDATE_STAGE
from api.decision_service_client import record_decision
from api.field_context import _field_weather_context
from api.irrigation_engineering_workspace import (
    build_manual_source,
    manual_canonical_location,
    manual_canonical_snapshot,
    validate_manual_weather_date,
)
from api.irrigation_models import FieldIrrigationRequest, IrrigationRecommendationRequest
from api.irrigation_recommendation_policy import recommend_irrigation
from api.irrigation_state_guard import assess_irrigation_state
from api.main import (
    Permission,
    UserSchema,
    get_current_user,
    has_permission,
    require_permission,
    tenant_connection,
)
from api.soil_enrichment import extract_texture, soil_water_provenance
from api.soil_water import soil_water_params
from api.weather_advice import precipitation_incomplete_detail
from api.weather_service_client import (
    et0_provenance as _et0_provenance,
)
from api.weather_service_client import (
    et0_unavailable_field_response,
    et0_unavailable_http_exception,
    field_irrigation_weather_snapshot,
    get_weather_forecast,
)
from api.weather_service_client import (
    get_irrigation_et0_product as _engine_et0,
)

router = APIRouter()


async def persist_manual_specification(conn, source: dict, user_id: str) -> None:
    """Append-only v185 storage; deterministic identity makes retries harmless."""
    spec = source["specification"]
    await conn.execute(
        """INSERT INTO irrigation_system_specifications
           (specification_id,tenant_id,field_id,season_id,system_id,specification,content_digest,created_by)
           VALUES ($1,$2::uuid,$3,$4,$5,$6::jsonb,$7,$8::uuid)
           ON CONFLICT (tenant_id,system_id,content_digest) DO NOTHING""",
        "manual_spec_" + source["specification_digest"],
        spec["tenant_id"],
        source["field_id"],
        source["season_id"],
        source["system_id"],
        json.dumps(spec),
        source["specification_digest"],
        user_id,
    )


_LOG = logging.getLogger("sahool.irrigation.et0")

# رموز حالة المحرّك المتعذّر ⇒ فشل مُغلَق (لا حساب ET0 محلّيّ بديل).
_ENGINE_DOWN_CODES = (502, 503, 504)


async def _field_weather_snapshot(latitude_deg: float, longitude_deg: float) -> dict:
    return await field_irrigation_weather_snapshot(
        latitude_deg, longitude_deg, forecast_loader=get_weather_forecast
    )


async def _submit_candidate_to_decision(payload: dict, tenant_id: str | None) -> dict:
    """يقدّم المرشَّح إلى خدمة القرار (تسجيل معلَّق للموافقة) — نقطة وصل قابلة للـmonkeypatch.

    **لا ينفّذ**: يُسجّل قراراً معلَّقاً (pending_approval) فقط؛ التنفيذ المحروس (حواجز +
    human-in-loop + طابور) يبقى في مسار decision_dispatch. تعذّر الخدمة ⇒ HTTPException.
    """
    return await record_decision(payload, tenant_id=tenant_id)


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
    **والمطر إلزاميّ**: حذفُه ⇒ 503 بنفس شكل خطأ نقص المطر في بقيّة المنصّة، لا صفر.
    """
    # قبل ET0 عمداً: نقصُ المطر عطلُ **مُدخَلٍ** لا عطلُ اعتماديّة، فلا يُنفَق عليه نداءُ
    # شبكةٍ ولا يُبلَّغ برسالة «المحرّك غير متاح» — تشخيصٌ يسمّي غيرَ سببه يُطيل العطل.
    missing_rain = [
        index
        for index, value in enumerate((req.rain_recent_mm, req.forecast_rain_mm))
        if value is None
    ]
    if missing_rain:
        raise HTTPException(
            status_code=503,
            detail=precipitation_incomplete_detail(
                context="irrigation_recommendation", missing_intervals=missing_rain
            ),
        )

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
            tenant_id=getattr(user, "tenant_id", None),
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503,
                detail="weather-engine ET0 unavailable — fail-closed (no local ET0 fallback)",
            ) from exc
        raise
    et0_mm = et0_prod.get("et0_mm")
    if et0_mm is None:
        # المحرّك رفض مُدخَلاً مستحيلاً (422) أو لم يُعِد ET0 (503) — لا float(None) ⇒ 500.
        raise et0_unavailable_http_exception(et0_prod)
    recommendation = recommend_irrigation(
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
    return {**recommendation, "et0": _et0_provenance(et0_prod)}


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

    canonical = None
    if req.manual_execution:
        if not has_permission(user, Permission.IRRIGATION_MANAGE):
            raise HTTPException(
                status_code=403, detail="manual irrigation specification requires irrigation manage"
            )
        if req.has_manual_evidence_overrides():
            raise HTTPException(
                status_code=422, detail="manual execution needs server water and weather evidence"
            )

    async with tenant_connection(user) as conn:
        # سياق الحقل + الموسم النشط (يرفع 404 إن غاب الحقل).
        field_lat, field_lon, crop, stage, _days = await _field_weather_context(conn, field_id)
        season = await conn.fetchrow(
            "SELECT season_id FROM seasons WHERE field_id = $1 AND status = 'active' "
            "ORDER BY created_at DESC LIMIT 1",
            field_id,
        )
        season_id = season["season_id"] if season else None
        if req.manual_execution:
            from api.canonical_water_state import (
                MAX_LEDGER_AGE_HOURS,
                CanonicalWaterState,
                resolve_canonical_water_state,
            )

            resolved = await resolve_canonical_water_state(
                conn, tenant_id=str(user.tenant_id), field_id=field_id
            )
            if not isinstance(resolved, CanonicalWaterState) or not resolved.operational_eligible:
                raise HTTPException(
                    status_code=409, detail="manual_canonical_water_not_operational"
                )
            try:
                canonical = manual_canonical_snapshot(
                    resolved.to_dict(),
                    str(season_id),
                    req.manual_execution.season_id,
                    MAX_LEDGER_AGE_HOURS,
                )
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        # أحدث استنزاف + عمره (نضارة) — مفقود يبقى None (لا صفر مُختلَق).
        lrow = await conn.fetchrow(
            "SELECT depletion_mm, confidence, soil_moisture_pct, ledger_date, decision, "
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
    # UNRECORDED-IRRIGATION-READ-AS-ZERO-APPLIED-WATER-01: ثقةُ القيد المنخفضة لا تقول
    # **لماذا**. قيدٌ آليٌّ بلا صفِّ ريّ استنزافُه حدٌّ أعلى (الريُّ قُرِئ صفراً لأنّه
    # مجهول) — يُسمّى في المخرَج ولا يُخصَم مرّةً ثانية من الثقة (القيدُ خصمه أصلاً).
    from api.water_ledger_auto import (
        APPLIED_WATER_UNRECORDED,
        APPLIED_WATER_VOLUME_UNTRACKED,
        applied_water_status,
        ledger_notes_from_decision,
    )

    ledger_notes = ledger_notes_from_decision(lrow.get("decision")) if lrow else None
    applied_status = applied_water_status(ledger_notes) if ledger_notes is not None else None
    applied_water_limitations: list[str] = []
    if applied_status == APPLIED_WATER_UNRECORDED:
        applied_water_limitations.append(
            "applied_water_unrecorded — لا سجلَّ ريٍّ لهذا الحقل في يوم القيد: الريُّ في "
            "الميزان مجهولٌ لا صفر، فالاستنزافُ وكمّيّةُ الريّ الموصى بها حدٌّ أعلى. "
            "سجّل الريّات أو أعلِن مصدرَ الماء قبل الاعتماد."
        )
    elif applied_status == APPLIED_WATER_VOLUME_UNTRACKED:
        applied_water_limitations.append(
            "applied_water_volume_untracked — رُصدت ريّةٌ بلا حجم: الماءُ المضاف أدنى "
            "تقدير، فالاستنزافُ وكمّيّةُ الريّ الموصى بها حدٌّ أعلى."
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
    if canonical is not None:
        # The manual target uses one server-owned root-zone/water state, not a client fallback.
        if (
            applied_status != "recorded"
            or depletion_mm is None
            or float(depletion_mm) != canonical["depletion_mm"]
            or str(ledger_date) != canonical["ledger_date"]
        ):
            raise HTTPException(status_code=409, detail="manual_water_changed_or_applied_unknown")
        depletion_mm = canonical["depletion_mm"]
        dep_conf = canonical["depletion_confidence"]
        ledger_age_hours = canonical["ledger_age_hours"]
        taw_mm = canonical["taw_mm"]
        sw = {**sw, "raw_fraction": canonical["raw_fraction"]}
        taw_source = "canonical_root_zone_profile"
        crop = canonical["crop"]
        stage = canonical["growth_stage"]
        soil_prov = {
            **soil_prov,
            "confidence_penalty": 0.0,
            "taw": {"source": taw_source},
            "canonical_evidence": canonical["evidence"],
        }

    state = assess_irrigation_state(
        depletion_mm=depletion_mm,
        taw_mm=taw_mm,
        ledger_age_hours=ledger_age_hours,
        taw_source=taw_source,
    )
    if stage is None:
        state = {
            **state,
            "available": False,
            "status": "insufficient_data" if state["available"] else state["status"],
            "limitations": [*state["limitations"], "growth_stage_unavailable"],
        }

    inputs = {
        "depletion_mm": round(float(depletion_mm), 2) if depletion_mm is not None else None,
        "taw_mm": taw_mm,
        "raw_fraction": sw["raw_fraction"],
        "depletion_fraction": state["depletion_fraction"],
        "taw_source": taw_source,
        "soil_provenance": soil_prov,
        "ledger_age_hours": round(ledger_age_hours, 1) if ledger_age_hours is not None else None,
        # None = القيدُ لم يُعلِن (يدويّ/قديم) — لا يُفترَض «مُسجَّلاً».
        "applied_water_status": applied_status,
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
    if canonical is not None:
        try:
            field_lat, field_lon, _elev_default_m = manual_canonical_location(canonical)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

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
                # التجاوزُ اليدويّ يحمل مطرَه أيضاً. وإلّا كان «تجاوزُ حرارة» يُسقِط
                # المطرَ ضمناً إلى صفر — فيصير المسارُ الاحتياطيّ أكثرَ إذناً بالريّ
                # من الأساسيّ، وهو عكسُ ما يُنتظَر من تجاوزٍ يدويّ.
                "rain_recent_mm": req.rain_recent_mm,
                "forecast_rain_mm": req.forecast_rain_mm,
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

    # ومطرٌ ناقصٌ يقف حيث تقف الحرارة. كان هذا المسارُ **لا يمرّر المطرَ أصلاً**، فتأخذه
    # النواةُ صفراً — والصفرُ يُنقِص المطروحَ من الحاجة فيرفع الكمّيّة: انحيازٌ في اتّجاه
    # الإذن بالريّ، صامتٌ في المخرَج. وتوثيقُ هذه الدالّة يقول «**صدق:** مفقود ≠ صفر» —
    # وكان صادقاً عن الاستنزاف والتربة، ساكتاً عن المطر.
    if wx.get("rain_recent_mm") is None or wx.get("forecast_rain_mm") is None:
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
                precipitation_incomplete_detail(
                    context="field_irrigation_recommendation",
                    missing_intervals=[
                        i
                        for i, key in enumerate(("rain_recent_mm", "forecast_rain_mm"))
                        if wx.get(key) is None
                    ],
                )["message_ar"],
            ],
            "calibrated": False,
        }

    # Manual source uses canonical elevation and a current dated server forecast.
    if canonical is not None:
        try:
            validate_manual_weather_date(wx, date.today())
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    # ET0 from the weather engine; legacy nonmanual elevation remains unchanged.
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
            tenant_id=getattr(user, "tenant_id", None),
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
    if et0_mm is None:
        # طقس الحقل نفسه رُفض أو نقص: فشل مُغلَق بأسباب المحرّك بدل float(None) ⇒ 500.
        return et0_unavailable_field_response(
            et0_prod, field_id, season_id, inputs, evidence_ids, state["limitations"]
        )
    evidence_ids.append(f"weather-engine-et0:{et0_prod.get('weather_snapshot_id')}")

    rec = recommend_irrigation(
        et0_mm=et0_mm,
        crop=crop,
        stage=stage,
        rain_recent_mm=wx["rain_recent_mm"],
        forecast_rain_mm=wx["forecast_rain_mm"],
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
    if req.submit_to_decision and (
        et0_prod.get("method") != "fao56_penman_monteith"
        or et0_prod.get("quality_status") != "validated"
    ):
        # Input acceptance is not regional calibration. Keep fallback/degraded ET0
        # visible as advisory, but do not persist an execution specification or
        # submit it into the governed decision chain.
        approval_state = "blocked_et0_advisory_only"
        submit_limitation = (
            "et0_advisory_only — لم يُقدَّم: ET0 تقديري أو غير مكتمل الجودة؛ "
            "قبول مدخلات Penman–Monteith لا يثبت معايرة محلية."
        )
    elif req.submit_to_decision and rec["forecast_hold"] and rec["should_irrigate"] is None:
        # حجزُ المطر يمنع التقديم. المرشَّحُ الذي لا قرارَ فيه (`should_irrigate=None`)
        # ليس شيئاً يُعتمَد؛ وتقديمُه كان سيُنتِج سجلَّ موافقةٍ على امتناع.
        approval_state = "blocked_forecast_rain_hold"
        submit_limitation = (
            "forecast_rain_hold_requires_reassessment — لم يُقدَّم: مطرٌ متوقَّعٌ يؤجّل الريّ "
            "بينما بلغ الاستنزافُ عتبةَ الإطلاق. أعِد التقييم بعد المطر."
        )
    elif req.submit_to_decision and (
        rec["should_irrigate"] is not True or rec.get("requires_expert_review")
    ):
        # IRRIGATION-CANDIDATE-HAS-NO-LINEAGE-01: مرشّحٌ لا يوصي بالريّ، أو يشترط خبيراً (ملوحةٌ حرجة)،
        # ليس شيئاً يعتمده المراجِع العامّ — كان يُقدَّم ويُعتمَد لأنّ المرشّح لا يحمل هذين الحقلين.
        approval_state = (
            "blocked_requires_expert_review"
            if rec.get("requires_expert_review")
            else "blocked_not_recommending_irrigation"
        )
        submit_limitation = (
            "لم يُقدَّم: المرشّح يشترط مراجعةَ خبير (ملوحة حرجة)"
            if rec.get("requires_expert_review")
            else "لم يُقدَّم: التوصية لا تقترح ريّاً — لا شيء يُعتمَد"
        )
    elif req.submit_to_decision:
        # **عقدُ التسجيل هو عقدُ `crop_decision_bridge` نفسُه.** كان هذا المسار يرسل
        # `recommendation` و`status` — حقلين لا يقرؤهما المُسجِّل — فتُحفَظ قيمةٌ فارغة،
        # ثمّ يُستنتَج `pending_approval` **محلّيّاً** من غياب استثناء. أي إعلانُ نجاحٍ
        # بلا شاهدٍ عليه، في مسارٍ يقود إلى ماءٍ يُصرَف.
        candidate = {
            "decision_type": "irrigation",
            "field_id": field_id,
            "season_id": season_id,
            "status": "pending_approval",
            "approval_required": True,
            "recommendation": {
                "should_irrigate": rec["should_irrigate"],
                "trigger_reason": rec["trigger_reason"],
                "net_irrigation_mm": rec["net_irrigation_mm"],
                "target_refill_mm": rec["target_refill_mm"],
                "urgency": rec["urgency"],
                # `timing_ar`/`rationale_ar` هما الموضعان الوحيدان اللذان يذكران المطرَ
                # المتوقَّع للمزارع. حجبُهما كان يجعل الحجزَ صامتاً: قرارٌ يُمتنَع عنه بلا سبب.
                "timing_ar": rec["timing_ar"],
                "rationale_ar": rec["rationale_ar"],
                "forecast_hold": rec["forecast_hold"],
            },
            "confidence": confidence,
            "evidence_ids": evidence_ids,
            "provenance": {
                "et0": et0_prod.get("weather_snapshot_id"),
                "et0_product": _et0_provenance(et0_prod),
                "weather": wx.get("valid_time"),
                "taw_source": taw_source,
                "applied_water_status": applied_status,
            },
            "calibrated": False,
            "policy": rec.get("policy"),
            "requires_expert_review": bool(rec.get("requires_expert_review")),
        }
        if req.manual_execution:
            try:
                source = build_manual_source(
                    intent=req.manual_execution,
                    tenant_id=str(user.tenant_id),
                    field_id=field_id,
                    season_id=str(season_id),
                    canonical=canonical,
                    applied_status=applied_status,
                    recommendation=rec,
                    weather=wx,
                    et0=et0_prod,
                )
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            # Persist the declared specification before submission. It is not an approval;
            # decision-service reviews the exact source, including declaration provenance.
            async with tenant_connection(user) as conn:
                await persist_manual_specification(conn, source, str(user.user_id))
            candidate["manual_execution_source"] = source
        # IRRIGATION-CANDIDATE-HAS-NO-LINEAGE-01: بلا `candidate_lineage_id` كان الاعتمادُ يفشل دائماً
        # (`candidate_lineage_mismatch` — NULL لا يساوي شيئاً). النَّسَبُ بصمةُ المحتوى نفسِه (نمطُ MPC)،
        # والمعرّفُ حتميٌّ منه، فإعادةُ التقديم بالمحتوى نفسِه إعادةٌ لا مرشّحٌ ثانٍ.
        content_digest = hashlib.sha256(
            json.dumps(candidate, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        candidate["content_digest"] = content_digest
        candidate["candidate_lineage_id"] = "irr_" + content_digest[:16]
        tenant_key = str(getattr(user, "tenant_id", "") or "")
        record_payload = {
            "decision_id": "dec_irr_"
            + hashlib.sha256(f"{tenant_key}:{field_id}:{content_digest}".encode()).hexdigest()[:24],
            "field_id": field_id,
            "season_id": season_id,
            "decision_type": "irrigation",
            "stage": CANDIDATE_STAGE,
            "decision_value": candidate,
            "created_by": getattr(user, "username", None) or getattr(user, "user_id", None),
        }
        try:
            res = await _submit_candidate_to_decision(
                record_payload, getattr(user, "tenant_id", None)
            )
            decision_id = res.get("decision_id") or res.get("id")
            # شاهدُ الحفظ لا غيابُ الاستثناء: نقطةُ التسجيل لا تُعيد `status`، فاستنتاجُ
            # `pending_approval` منها محلّيّاً كان يُعلِن نجاحاً لم يُثبَت.
            proven = (
                res.get("authoritative") is True
                and res.get("persisted") is True
                and bool(decision_id)
                and res.get("stage") == CANDIDATE_STAGE
            )
            if proven:
                approval_state = "pending_approval"
            else:
                decision_id = None
                approval_state = "submit_unproven"
                submit_limitation = (
                    "decision-service did not confirm authoritative persistence of the "
                    "pending_approval candidate — fail-closed (not submitted)"
                )
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
            # `timing_ar`/`rationale_ar` هما الموضعان الوحيدان اللذان يذكران المطرَ
            # المتوقَّع للمزارع. حجبُهما كان يجعل الحجزَ صامتاً: قرارٌ يُمتنَع عنه بلا سبب.
            "timing_ar": rec["timing_ar"],
            "rationale_ar": rec["rationale_ar"],
            "forecast_hold": rec["forecast_hold"],
            "policy_knobs": rec["policy_knobs"],
        },
        "et0": _et0_provenance(et0_prod),
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
            *applied_water_limitations,
            *([weather_limitation] if weather_limitation else []),
            *([submit_limitation] if submit_limitation else []),
        ],
        "calibrated": False,
    }
