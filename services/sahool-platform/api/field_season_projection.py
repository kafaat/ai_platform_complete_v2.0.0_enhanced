"""api/field_season_projection.py — الحقيقة التشغيليّة الموحّدة للحقل-الموسم — VNext الموحِّد.

يجمع محرّكات الموسم النقيّة القائمة في **قراءة واحدة** لكلّ ``(field_id, season_id)`` — بدل أن
يستدعي الذكاء/الواجهة/التقارير مصادر متفرّقة، يقرؤون «حقيقة تشغيليّة» واحدة:

  ① حارس التقويم        ``api.season_calendar_guard.evaluate_season_calendar``  (داخل/خارج نافذة)
  ② الفينولوجيا الحراريّة ``core.gdd_phenology.phenology_progress``               (المرحلة + GDD + تباعد)
  ③ Kc الطوريّ           ``core.season_phenology.stage_kc``                       (FAO-56)
  ④ مخاطر المرحلة        ``core.season_stage_risk.stage_weather_risks``           (طقس × مرحلة)
  ⑤ تعارض الاستشعار      ``core.eo_stage_mismatch.detect_eo_stage_mismatch``      (NDVI/NDMI × مرحلة)
  ⑦ النافذة الحرجة       ``gdd_phenology.project_next_critical_window``           (متى يدخل الطور الأضعف)
                        + ``season_stage_risk.critical_window_collisions``        (× التنبؤ ⇒ زمن قياديّ)
  + الماء (عجز 7/14 يوم) + المهام المفتوحة (تُمرَّر من القاعدة).

يقع في ``api/`` لأنّه يعتمد ``api.season_calendar_guard`` (الذي يعتمد بيانات تقويم في api)؛ فاستيراد
core منه سليم (api ← core)، عكسه ممنوع (core لا يستورد api). المرحلة الفعّالة = مرحلة GDD إن انطبقت،
وإلّا مرحلة الأيّام — وتُغذّي ④ و⑤.

و④ و⑦ يجيبان سؤالين مختلفين لا واحداً: ④ «هل الحقل في خطرٍ اليوم؟» بقيمٍ مجمَّعة على المرحلة
الجارية · ⑦ «متى سيصادف طورُه الأضعف طقساً متطرّفاً؟» بنافذةٍ مؤرَّخة وزمنٍ قياديّ. والفرق بينهما
هو ما يسمح بإجراءٍ تحضيريّ بدل إسعافيّ.

**نقيّ (لا شبكة/قاعدة):** يستقبل المُدخَلات الخام ويُخرِج القاموس الموحّد. طبقة القراءة من القاعدة
(تجمع المُدخَلات ثمّ تنادي هذه الدالّة) رقيقة وتُبنى لاحقاً مع بطاقة أدلّة الموسم.

صدق: كلّ مكوّن يحمل ثقته وأدلّته الناقصة؛ الموحِّد يجمعها. المُدخَل الغائب ⇒ الكتلة None/inconclusive
+ يُدرَج في ``evidence_missing`` — لا رقم مُختلَق. ``season_confidence`` سقفها MEDIUM (كلّه تقدير/توقّع).
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import date, timedelta

from core.eo_stage_mismatch import detect_eo_stage_mismatch
from core.gdd_phenology import (
    phenology_progress,
    project_next_critical_window,
    stage_equivalent_day,
)
from core.season_phenology import resolve_crop_id, stage_kc
from core.season_stage_risk import critical_window_collisions, stage_weather_risks
from fastapi import HTTPException

from api.season_calendar_guard import evaluate_season_calendar


def _safe_max_stamp(stamps: list[object]) -> object | None:
    """Returns the latest comparable stamp without fabricating time when types differ."""
    present = [s for s in stamps if s is not None]
    if not present:
        return None
    try:
        return max(present)
    except TypeError:
        # Mixed datetime/string values can happen in tests or partial adapters. Keep the last
        # supplied non-null value rather than inventing a normalized timestamp.
        return present[-1]


def _summarize_reconciled_outcomes_for_season(
    outcome_records: list[dict] | None,
    recommendation_outcomes: list[dict] | None,
    *,
    dispatch_links: dict | None = None,
) -> dict:
    """Compact, read-path view of reconciled outcomes for the season projection.

    Truthfulness rules:
      * `success_rate` is computed only from decided outcomes (`success is True/False`).
      * pending / immature recommendation outcomes stay pending and never inflate samples.
      * the source mix is exposed, so consumers can see whether evidence came from
        decision effects, yield-learning outcomes, or both.
    """
    from core.outcome_reconciler import reconcile_outcomes

    reconciled = reconcile_outcomes(
        outcome_records or [],
        recommendation_outcomes or [],
        dispatch_links=dispatch_links or {},
    )
    decided = succeeded = failed = pending = 0
    stamps: list[object] = []
    for item in reconciled["unified"]:
        stamps.append(item.get("recorded_at"))
        success = item.get("success")
        if success is True:
            decided += 1
            succeeded += 1
        elif success is False:
            decided += 1
            failed += 1
        else:
            pending += 1

    return {
        "enabled": True,
        "total": reconciled["total"],
        "decided": decided,
        "succeeded": succeeded,
        "failed": failed,
        "pending": pending,
        "success_rate": round(succeeded / decided, 3) if decided else None,
        "sample_count": decided,
        "by_source": reconciled["by_source"],
        "by_kind": reconciled["by_kind"],
        "linked_group_count": len(reconciled["linked_groups"]),
        "latest_recorded_at": _safe_max_stamp(stamps),
        "authoritative_note": reconciled["authoritative_note"],
    }


def archive_forecast_gap_days(
    accumulated_gdd_through: date | str | None, forecast_daily: list[dict] | None, ref: date
) -> int | None:
    """Days between the last day of the thermal sum and the first forecast day (0 = continuous).

    ``None`` when the caller declares no coverage date (the sum is then taken to run to the
    day before the forecast, as before). The first forecast day is the first row's ``date``
    when it parses, otherwise ``ref``.
    """
    if accumulated_gdd_through is None:
        return None
    try:
        through = (
            accumulated_gdd_through
            if isinstance(accumulated_gdd_through, date)
            else date.fromisoformat(str(accumulated_gdd_through))
        )
    except ValueError:
        return None
    first = ref
    if forecast_daily:
        try:
            first = date.fromisoformat(str(forecast_daily[0].get("date")))
        except (TypeError, ValueError):
            first = ref
    return max(0, (first - through).days - 1)


def assemble_field_season_state(
    *,
    field_id: str | None = None,
    season_id: str | None = None,
    crop: str | None = None,
    cultivar: str | None = None,
    sowing_date: date | None = None,
    season_end: date | None = None,
    today: date | None = None,
    accumulated_gdd: float | None = None,
    observed_ndvi: float | None = None,
    imagery_date: date | None = None,
    observed_ndmi: float | None = None,
    valid_pixel_ratio: float | None = None,
    cloud_pct: float | None = None,
    weather_signals: dict | None = None,
    water_deficit_7d_mm: float | None = None,
    water_deficit_14d_mm: float | None = None,
    water_stress_factor: float | None = None,
    open_tasks_count: int | None = None,
    forecast_daily: list[dict] | None = None,
    accumulated_gdd_through: date | str | None = None,
    outcome_records: list[dict] | None = None,
    recommendation_outcomes: list[dict] | None = None,
    dispatch_links: dict | None = None,
) -> dict:
    """يبني الحقيقة التشغيليّة الموحّدة للحقل-الموسم من مُدخَلات خام. نقيّ.

    يُعيد قاموساً واحداً يحمل: الهويّة، المرحلة الفعّالة، أيّام البذار، GDD، حالة التقويم،
    Kc الحاليّ، عجز الماء 7/14 يوم، تعارض الاستشعار، مخاطر المرحلة، المهام المفتوحة،
    ``season_confidence``، و``evidence_used``/``evidence_missing`` المُجمَّعة.
    """
    crop_id = resolve_crop_id(crop)
    ref = today or date.today()
    days_after_sowing = (ref - sowing_date).days if sowing_date is not None else None

    # ① التقويم
    calendar = evaluate_season_calendar(crop, sowing_date, season_end)
    # ② الفينولوجيا الحراريّة (+ الأيّام)
    pheno = phenology_progress(crop_id, days_after_sowing, accumulated_gdd)
    # المرحلة الفعّالة من المحلِّل الواحد: GDD إن انطبقت وتوفّرت، وإلّا الأيّام (احتياط مُعلَن).
    effective_stage = pheno.get("stage")
    stage_source = pheno.get("stage_source")
    # ③ Kc الطوريّ
    # Kc على منحنى البطاقة في الموضع الموافق للمرحلة المحلَّلة (حراريّة أو تقويميّة)، لكي لا
    # يقول الردّ «مرحلة late» مع Kc مرحلةٍ تقويميّة أخرى.
    kc_day = stage_equivalent_day(crop_id, days_after_sowing, pheno)
    current_kc = stage_kc(crop_id, kc_day if kc_day is not None else days_after_sowing)

    # ④ مخاطر المرحلة (تُغذّى بالطقس + الماء)
    risk_signals = dict(weather_signals or {})
    if water_stress_factor is not None:
        risk_signals.setdefault("water_stress_factor", water_stress_factor)
    if water_deficit_7d_mm is not None:
        risk_signals.setdefault("water_deficit_mm", water_deficit_7d_mm)
    stage_risk = stage_weather_risks(effective_stage, crop_id, risk_signals)

    # ⑤ تعارض الاستشعار مع المرحلة
    eo_stage = effective_stage
    if imagery_date is not None and imagery_date != ref:
        # Historical imagery cannot be compared to a later crop stage or later GDD.
        scene_age = (imagery_date - sowing_date).days if sowing_date is not None else None
        eo_stage = phenology_progress(crop_id, scene_age, None).get("days_stage")
    eo = detect_eo_stage_mismatch(
        eo_stage,
        observed_ndvi,
        observed_ndmi,
        valid_pixel_ratio=valid_pixel_ratio,
        cloud_pct=cloud_pct,
    )

    # ⑥ النتائج المتصالحة (Decision outcome + Recommendation yield-learning)
    outcome_reconciliation = _summarize_reconciled_outcomes_for_season(
        outcome_records,
        recommendation_outcomes,
        dispatch_links=dispatch_links,
    )

    # ⑦ النافذة الحرجة القادمة × التنبؤ اليوميّ (W1+W2)
    # يجيب «متى» لا «ما الطور»: ④ أعلاه يقيس خطرَ اليوم على المرحلة الجارية، وهذا
    # يقيس هل سيصادف الطورُ الأضعف طقساً متطرّفاً — والفرق بينهما الزمن القياديّ.
    # سلسلةُ GDD اليوميّة **مملوكةٌ للطقس** (WS-C.1c): تُستقبَل ولا تُحسَب هنا.
    daily = list(forecast_daily or [])
    # The thermal sum and the forecast GDD series are added together only when they are
    # continuous. The archive trails real time (reanalysis lag), so a sum through
    # today-5 followed by a forecast from today leaves days nobody counted; adding the
    # two would project the window late by exactly those days (the dangerous direction:
    # a field already flowering reported "upcoming", its collisions ignored). A declared
    # gap drops the series, so the window comes from the sum alone or from the calendar,
    # and says why.
    gap_days = archive_forecast_gap_days(accumulated_gdd_through, daily, ref)
    use_series = bool(daily) and accumulated_gdd is not None and not gap_days
    critical_window = project_next_critical_window(
        crop_id,
        accumulated_gdd=accumulated_gdd,
        forecast_daily_gdd=[d.get("gdd") for d in daily] if use_series else None,
        sowing_date=sowing_date,
        today=ref,
    )
    if gap_days and accumulated_gdd is not None:
        critical_window["evidence_missing"].append("archive_forecast_gap")
        critical_window["archive_forecast_gap_days"] = gap_days
    window_collisions = critical_window_collisions(
        crop_id, critical_window, daily or None, today=ref
    )

    # ── تجميع الأدلّة (صدق: ما توفّر مقابل ما نقص من الإشارات الجوهريّة) ──
    core_signals = {
        "crop": crop_id is not None,
        "sowing_date": sowing_date is not None,
        "days_after_sowing": days_after_sowing is not None,
        "accumulated_gdd": accumulated_gdd is not None,
        "ndvi": observed_ndvi is not None,
        "weather": bool(weather_signals),
        "water": water_stress_factor is not None
        or water_deficit_7d_mm is not None
        or water_deficit_14d_mm is not None,
        "open_tasks": open_tasks_count is not None,
        "outcomes": outcome_reconciliation["total"] > 0,
    }
    evidence_used = [k for k, present in core_signals.items() if present]
    evidence_missing = [k for k, present in core_signals.items() if not present]

    # ── ثقة الموسم: سقف MEDIUM. منخفضة إن جُهِلت المرحلة أو ندرت الإشارات الحيّة. ──
    live = sum(1 for k in ("ndvi", "weather", "water") if core_signals[k])
    season_confidence = "low" if (effective_stage is None or live == 0) else "medium"

    return {
        "schema": "field_season_state.v1",
        "field_id": field_id,
        "season_id": season_id,
        "crop": crop_id,
        "crop_input": crop,
        "cultivar": cultivar,
        # الطور
        "current_stage": effective_stage,
        "current_stage_ar": pheno.get("stage_ar"),
        "stage_source": stage_source,  # gdd | days | None
        "stage_fallback": pheno.get("stage_fallback"),  # calendar_days | None
        "stage_fallback_reason": pheno.get("stage_fallback_reason"),
        "days_after_sowing": days_after_sowing,
        "accumulated_gdd": accumulated_gdd,
        "accumulated_gdd_through": (
            accumulated_gdd_through.isoformat()
            if isinstance(accumulated_gdd_through, date)
            else accumulated_gdd_through
        ),
        "gdd_to_maturity": pheno.get("gdd_to_maturity"),
        "gdd_fraction": pheno.get("gdd_fraction"),
        "phenology_divergence": pheno.get("divergence"),
        "current_kc": current_kc,
        # التقويم
        "calendar_status": calendar.get("status"),
        "calendar": calendar,
        # الماء
        "water_deficit_7d_mm": water_deficit_7d_mm,
        "water_deficit_14d_mm": water_deficit_14d_mm,
        "water_stress_factor": water_stress_factor,
        # الاستشعار × المرحلة
        "eo_stage_mismatch": eo,
        # مخاطر المرحلة (طقس × مرحلة) — خطرُ اليوم على المرحلة الجارية
        "weather_stage_risks": stage_risk,
        # النافذة الحرجة القادمة × التنبؤ — «متى» بزمنٍ قياديّ (W1+W2)
        "critical_window": critical_window,
        "critical_window_collisions": window_collisions,
        # العمليّات
        "open_operations": open_tasks_count,
        # النتائج/التعلّم — لا ترفع الثقة وحدها؛ المعلّقة مُعلنة ولا تدخل success_rate.
        "outcome_reconciliation": outcome_reconciliation,
        # الحوكمة/الصدق
        "season_confidence": season_confidence,
        "requires_review": bool(
            calendar.get("requires_review")
            or stage_risk.get("requires_action")
            or eo.get("status") == "below_expected"
            or (pheno.get("divergence") or {}).get("diverged")
            or window_collisions.get("requires_action")
        ),
        "evidence_used": evidence_used,
        "evidence_missing": evidence_missing,
        "disclaimer_ar": (
            "حقيقة تشغيليّة مُجمَّعة من محرّكات تقديريّة (تقويم/GDD/FAO-56/طقس متوقّع/استشعار). "
            "السقف MEDIUM؛ الناقص مُعلَن في evidence_missing — لا رقم مُختلَق."
        ),
    }


# ── Pure helpers for the thin route ``GET /api/v1/fields/{id}/seasons/{sid}/state`` ──
# Moved out of ``api/routers/seasons.py`` (router size ratchet). They read nothing: every
# database query stays in the router, where the S5-EXEC-01 edge freeze records its evidence.


def reconciled_payload_is_bound(payload: dict, tenant: str, field_id: str, season_id: str) -> bool:
    """True only for an authoritative decision-service payload bound to this field-season.

    Every outcome row must belong to the tenant (and to the field, when it names one); every
    recommendation outcome must name this exact tenant, field and season.
    """
    return (
        payload.get("authoritative") is True
        and payload.get("tenant_id") == tenant
        and payload.get("field_id") == field_id
        and payload.get("season_id") == season_id
        and isinstance(payload.get("outcome_records"), list)
        and isinstance(payload.get("recommendation_outcomes"), list)
        and all(
            isinstance(r, dict)
            and r.get("tenant_id") == tenant
            and r.get("field_id") in (None, field_id)
            for r in payload["outcome_records"]
        )
        and all(
            isinstance(r, dict)
            and r.get("tenant_id") == tenant
            and r.get("field_id") == field_id
            and r.get("season_id") == season_id
            for r in payload["recommendation_outcomes"]
        )
    )


def first_season_crop(crops: object) -> str | None:
    """First crop of a ``seasons.crops`` value (JSON text or list); malformed ⇒ None."""
    if isinstance(crops, str):
        try:
            crops = json.loads(crops)
        except (ValueError, TypeError):
            crops = []
    return str(crops[0]) if isinstance(crops, list) and crops else None


def declare_outcome_sources(
    summary: dict, outcome_records: list | None, recommendation_outcomes: list | None
) -> None:
    """Declare in place which outcome sources were bound to the season."""
    # available: counts were computed from at least one season-bound source.
    # complete: both sources were bound to this season. Locally, decision outcomes are
    # unbound (no season without decision-service), so the platform is never complete.
    summary["available"] = outcome_records is not None or recommendation_outcomes is not None
    summary["complete"] = outcome_records is not None and recommendation_outcomes is not None
    summary["missing_sources"] = [
        name
        for name, rows in (
            ("outcome_record", outcome_records),
            ("recommendation_outcomes", recommendation_outcomes),
        )
        if rows is None
    ]


def blank_counts_when_unavailable(summary: dict) -> None:
    """No season-bound source ⇒ the counts are unknown (None), never a fabricated zero."""
    if not summary["available"]:
        for key in (
            "total",
            "decided",
            "succeeded",
            "failed",
            "pending",
            "sample_count",
            "linked_group_count",
        ):
            summary[key] = None


# ── Season weather inputs (W1-09: crop-2, weather-12) ──
# The route used to pass ``accumulated_gdd=None``, no forecast and no weather signals, so the
# stage was always calendar-only and ④/⑦ ran without weather. These helpers gather the three
# weather-service products after the route has released its database connection. The
# fetchers are injected (the route passes ``api.weather_service_client``), so this module
# still opens no network or database connection itself.

#: The weather-service historical view is ERA5 reanalysis, which trails real time by about
#: five days. Asking for the window up to today returns a truncated series, which
#: ``canonical_historical_days`` rightly refuses. The thermal sum therefore runs to
#: ``today - SEASON_ARCHIVE_LAG_DAYS`` and the state says so in ``accumulated_gdd_through``.
SEASON_ARCHIVE_LAG_DAYS = 5
SEASON_FORECAST_DAYS = 7
#: Per-call budget for the season weather reads, as for the canonical field-weather read.
SEASON_WEATHER_TIMEOUT_S = 8.0
_WEATHER_SOURCE_ERRORS = (HTTPException, ValueError, TypeError, KeyError, TimeoutError)
#: Stable order of ``unavailable`` reasons (the chains run concurrently).
_UNAVAILABLE_ORDER = (
    "field_location_missing",
    "sowing_date_missing",
    "crop_card_gdd_base_missing",
    "archive_window_inside_reanalysis_lag",
    "weather_historical_unavailable",
    "weather_gdd_unavailable",
    "weather_gdd_incomplete",
    "weather_forecast_unavailable",
    "forecast_gdd_unavailable",
)


def _finite_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    f = float(value)
    return f if math.isfinite(f) else None


def forecast_stage_signals(days: list[dict]) -> dict:
    """Weather signals for ④ from the forecast days; a key is present only when every day has it.

    A partial horizon is absence, never a smaller total: one missing rain day would turn
    "rain expected at harvest" into "no rain".
    """
    signals: dict = {}

    def column(key: str) -> list[float] | None:
        values = [_finite_or_none(d.get(key)) for d in days]
        return values if values and all(v is not None for v in values) else None

    if (tmax := column("temp_max_c")) is not None:
        signals["tmax_c"] = max(tmax)
    if (tmin := column("temp_min_c")) is not None:
        signals["tmin_c"] = min(tmin)
    if (wind := column("wind_max_kmh")) is not None:
        signals["wind_kmh"] = max(wind)
    if (rain := column("precipitation_mm")) is not None:
        signals["rain_mm_next_7d"] = round(sum(rain), 1)
    if (rh := column("rh_mean_pct")) is not None:
        signals["rh_pct"] = round(sum(rh) / len(rh), 1)
    return signals


def _validated_gdd_total(product: object, expected_days: int) -> float | None:
    """The engine's accumulated GDD only when every day was computed (degraded ⇒ None)."""
    from api.season_simulation import validated_engine_daily_series

    validated_engine_daily_series(product, "daily_gdd", expected_days)
    if product.get("quality_status") != "validated":  # type: ignore[union-attr]
        return None
    return _finite_or_none(product.get("accumulated_gdd"))  # type: ignore[union-attr]


async def gather_season_weather_inputs(
    *,
    crop: str | None,
    sowing_date: date | None,
    as_of: date,
    today: date,
    lat: float | None,
    lon: float | None,
    tenant_id: str,
    get_historical,
    get_gdd,
    get_forecast=None,
) -> dict:
    """Accumulated GDD (archive + engine GDD at the crop-card base), forecast and signals.

    Every source is optional for the state read: a failure leaves its value None and names
    the reason in ``unavailable``. No GDD is computed here; the weather engine is the only
    GDD kernel (WS-C.1c). The base temperature is the crop card's ``thermal.gdd_base_c`` —
    the same card whose ``gdd_to_maturity`` sets the stage thresholds — so the sum and the
    thresholds it is compared with share one policy.
    """
    from core.gdd_phenology import gdd_base_c

    from api.season_simulation import (
        canonical_historical_days,
        crop_gdd_policy,
        weather_product_provenance,
    )

    out: dict = {
        "accumulated_gdd": None,
        "accumulated_gdd_through": None,
        "archive_lag_days": SEASON_ARCHIVE_LAG_DAYS,
        "gdd_policy": None,
        "archive_provenance": None,
        "gdd_provenance": None,
        "forecast_daily": None,
        "weather_signals": None,
        "archive_forecast_gap_days": None,
        "unavailable": [],
    }
    missing = out["unavailable"]
    if lat is None or lon is None:
        missing.append("field_location_missing")
        return out
    if sowing_date is None:
        missing.append("sowing_date_missing")
        return out

    crop_id = resolve_crop_id(crop)
    base = gdd_base_c(crop_id)
    policy: dict | None = None
    if base is None:
        missing.append("crop_card_gdd_base_missing")
    else:
        _, cutoff = crop_gdd_policy(crop)
        policy = {
            "base_c": float(base),
            "base_source": "crop_card.thermal.gdd_base_c",
            "upper_cutoff_c": cutoff,
            "upper_cutoff_source": "season_simulation.crop_gdd_policy",
            "method": "modified",
        }
        out["gdd_policy"] = policy

    lat_f, lon_f = float(lat), float(lon)
    end = min(as_of, today - timedelta(days=SEASON_ARCHIVE_LAG_DAYS))

    async def bounded(awaitable):
        # Each weather call has its own short budget: the state read degrades to the calendar
        # rather than waiting for the client's 20 s default (W1-09 review, latency).
        return await asyncio.wait_for(awaitable, SEASON_WEATHER_TIMEOUT_S)

    async def archive_chain() -> None:
        if policy is None:
            return
        if end < sowing_date:
            missing.append("archive_window_inside_reanalysis_lag")
            return
        try:
            archive = await bounded(
                get_historical(
                    lat_f,
                    lon_f,
                    start_date=sowing_date.isoformat(),
                    end_date=end.isoformat(),
                    tenant_id=tenant_id,
                )
            )
            days = canonical_historical_days(archive, start=sowing_date, end=end)
            out["archive_provenance"] = weather_product_provenance("archive", archive)
        except _WEATHER_SOURCE_ERRORS:
            missing.append("weather_historical_unavailable")
            return
        try:
            product = await bounded(
                get_gdd(
                    daily_t_min=[d.t_min_c for d in days],
                    daily_t_max=[d.t_max_c for d in days],
                    base_c=policy["base_c"],
                    upper_cutoff_c=policy["upper_cutoff_c"],
                    method=policy["method"],
                    start_date=sowing_date.isoformat(),
                    end_date=end.isoformat(),
                    tenant_id=tenant_id,
                )
            )
            total = _validated_gdd_total(product, len(days))
        except _WEATHER_SOURCE_ERRORS:
            missing.append("weather_gdd_unavailable")
            return
        if total is None:
            missing.append("weather_gdd_incomplete")
            return
        out["accumulated_gdd"] = round(total, 1)
        out["accumulated_gdd_through"] = end.isoformat()
        out["gdd_provenance"] = weather_product_provenance("engine_gdd", product)

    async def forecast_chain() -> None:
        # The forecast describes what comes after today; a closed season has no use for it,
        # and a caller that needs only the stage passes no forecast fetcher.
        if as_of != today or get_forecast is None:
            return
        try:
            forecast = await bounded(get_forecast(lat_f, lon_f, days=SEASON_FORECAST_DAYS))
            rows = forecast.get("days")
            if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
                raise ValueError("forecast has no daily rows")
        except _WEATHER_SOURCE_ERRORS:
            missing.append("weather_forecast_unavailable")
            return
        rows = rows[:SEASON_FORECAST_DAYS]
        daily = [
            {
                "date": r.get("date"),
                "tmax_c": _finite_or_none(r.get("temp_max_c")),
                "tmin_c": _finite_or_none(r.get("temp_min_c")),
                "gdd": None,
            }
            for r in rows
        ]
        if policy is not None:
            try:
                fc_gdd = await bounded(
                    get_gdd(
                        daily_t_min=[d["tmin_c"] for d in daily],
                        daily_t_max=[d["tmax_c"] for d in daily],
                        base_c=policy["base_c"],
                        upper_cutoff_c=policy["upper_cutoff_c"],
                        method=policy["method"],
                        start_date=daily[0]["date"],
                        end_date=daily[-1]["date"],
                        tenant_id=tenant_id,
                    )
                )
                if _validated_gdd_total(fc_gdd, len(daily)) is None:
                    raise ValueError("forecast GDD incomplete")
                for d, g in zip(daily, fc_gdd["daily_gdd"], strict=True):
                    d["gdd"] = g
            except _WEATHER_SOURCE_ERRORS:
                missing.append("forecast_gdd_unavailable")
        out["forecast_daily"] = daily
        out["weather_signals"] = forecast_stage_signals(rows) or None

    # The two chains are independent (the forecast GDD needs only the policy), so they run
    # together: a stalled weather-service costs one budget per chain step, not the sum of all.
    await asyncio.gather(archive_chain(), forecast_chain())
    missing.sort(key=_UNAVAILABLE_ORDER.index)
    if out["accumulated_gdd_through"] is not None and out["forecast_daily"]:
        out["archive_forecast_gap_days"] = archive_forecast_gap_days(
            out["accumulated_gdd_through"], out["forecast_daily"], today
        )
    return out
