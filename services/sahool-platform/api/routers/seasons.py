"""api/routers/seasons.py — محاكاة الموسم (Seasons / season_simulation)
===============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: المسار/الأذونات/المخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

⚠ هذا الموجِّه للمسار ``/api/v1/seasons/{season_id}/simulate`` فقط؛ المسار المرتبط
بالحقل ``/api/v1/fields/{id}/seasons`` يبقى ضمن نطاق الحقول (routers/fields.py).

النموذج ``SeasonSimResponse`` والثابت ``_SIM_MAX_WINDOW_DAYS`` نُقِلا إلى
``api.season_models`` (تفكيك B1) ويُستورَدان من هناك؛ المساعِد ``_db_unavailable``
يبقى في ``api.main``. الاستيرادات الكسولة داخل الدالّة (openmeteo/season_simulation)
تبقى كما هي. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.season_models import _SIM_MAX_WINDOW_DAYS, SeasonSimResponse

router = APIRouter()
_TRUTHY = {"1", "true", "yes", "on"}


def _decision_context_mirror_enabled() -> bool:
    """Rollout guard: external AC-1 mirror is off until live SoR proof."""
    return os.getenv("HISTORICAL_SEASON_DECISION_CONTEXT_ENABLED", "0").strip().lower() in _TRUTHY


async def _load_linked_historical_inputs(
    conn, season_id: str, field_id: str, tenant_id, sowing_date, start, end
):
    """Read only an accepted, non-superseded manual record and qualified NDVI.

    The link trigger enforces tenant/field ownership. RLS on every table remains
    the authoritative isolation boundary.
    """
    record = await conn.fetchrow(
        "SELECT sr.* FROM season_record_links l "
        "JOIN season_records sr ON sr.id = l.season_record_id "
        "WHERE l.canonical_season_id = $1 AND l.field_id = $2 "
        "AND sr.trust_status = 'accepted' "
        "AND NOT EXISTS (SELECT 1 FROM season_record_links n "
        "                WHERE n.supersedes_link_id = l.link_id) "
        "ORDER BY l.linked_at DESC LIMIT 1",
        season_id,
        field_id,
    )
    # Safe migration path for existing data: auto-link only one unambiguous accepted
    # record with the same field and exact sowing day. Zero/multiple matches remain
    # unlinked; no fuzzy date or crop inference is allowed.
    if record is None and sowing_date is not None:
        candidates = await conn.fetch(
            "SELECT sr.* FROM season_records sr "
            "JOIN season_crop sc ON sc.season_id = sr.id "
            "WHERE sr.field_id = $1 AND sr.trust_status = 'accepted' "
            "AND sc.sowing_precision = 'day' AND sc.sowing_date = $2 "
            "AND NOT EXISTS (SELECT 1 FROM season_record_links l "
            "                WHERE l.season_record_id = sr.id) "
            "ORDER BY sr.accepted_at, sr.id LIMIT 2",
            field_id,
            sowing_date,
        )
        if len(candidates) == 1:
            record = candidates[0]
            await conn.execute(
                "INSERT INTO season_record_links "
                "(tenant_id, season_record_id, canonical_season_id, field_id, "
                " linkage_reason, linked_by) "
                "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT DO NOTHING",
                tenant_id,
                record["id"],
                season_id,
                field_id,
                "exact_field_and_sowing_day",
                "system:historical-season-composer",
            )
    crop = None
    events = []
    harvest = None
    if record is not None:
        crop = await conn.fetchrow("SELECT * FROM season_crop WHERE season_id = $1", record["id"])
        events = await conn.fetch(
            "SELECT * FROM season_events WHERE season_id = $1 ORDER BY event_date, id",
            record["id"],
        )
        harvest = await conn.fetchrow(
            "SELECT * FROM season_harvest WHERE season_id = $1", record["id"]
        )
    vegetation = await conn.fetch(
        "SELECT id, acquisition_date, ndvi_mean, cloud_pct, satellite, source "
        "FROM ndvi_timeseries WHERE field_id = $1 "
        "AND acquisition_date BETWEEN $2 AND $3 "
        "ORDER BY acquisition_date, id",
        field_id,
        start,
        end,
    )
    return record, crop, events, harvest, vegetation


@router.post("/api/v1/seasons/{season_id}/simulate", response_model=SeasonSimResponse)
async def simulate_season_endpoint(
    season_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يشغّل محاكاة محصوليّة (RUE/FAO-56) للموسم ويحفظ الناتج على صفّه.

    يؤكّد أنّ الموسم يخصّ المستأجِر (404 وإلّا)، يجمع المحصول/التواريخ من القاعدة
    والطقس التاريخي من Open-Meteo لنافذة الموسم (sowing→end أو آخر ~160 يوماً)،
    يستدعي api.season_simulation.simulate_season (نقيّ)، يكتب sim_* + sim_ran_at،
    ويردّ النتيجة (تقديرات بنطاق وثقة). 503 إن تعذّرت القاعدة أو الطقس.
    """
    import json as _json

    from api.connectors.openmeteo import fetch_historical
    from api.season_simulation import DayWeather, SimContext, simulate_season

    # ١) سياق الموسم من القاعدة (+ تأكيد المستأجِر عبر RLS ⇒ 404 إن غاب).
    try:
        async with tenant_connection(user) as conn:
            srow = await conn.fetchrow(
                "SELECT s.season_id, s.field_id, s.crops, s.sowing_date, s.season_end, "
                "f.lat, f.lon FROM seasons s JOIN fields f ON f.field_id = s.field_id "
                "WHERE s.season_id = $1",
                season_id,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة الموسم للمحاكاة", e) from e
    if srow is None:
        raise HTTPException(status_code=404, detail="الموسم غير موجود ضمن هذا المستأجِر")
    if srow["lat"] is None or srow["lon"] is None:
        raise HTTPException(
            status_code=422,
            detail="حقل الموسم بلا إحداثيّات (lat/lon) — لا يمكن جلب الطقس للمحاكاة.",
        )

    crops = srow["crops"]
    if isinstance(crops, str):
        try:
            crops = _json.loads(crops)
        except (ValueError, TypeError):
            crops = []
    crop_list = [str(c) for c in crops if str(c).strip()] if isinstance(crops, list) else []
    crop = crop_list[0] if crop_list else None
    # صدق (season_integrity #4): المحاكاة أحاديّة المحصول. زراعة مختلطة ⇒ تحذير صريح بأنّ
    # النتيجة تخصّ المحصول الأوّل فقط ولا تمثّل بقيّة المحاصيل — لا تجاهُل صامت.
    multi_crop_warning: str | None = None
    if len(crop_list) > 1:
        multi_crop_warning = (
            f"الموسم يضمّ {len(crop_list)} محاصيل ({'، '.join(crop_list)})؛ حوكِيَ المحصول "
            f"الأوّل فقط ({crop}). النتيجة لا تمثّل الزراعة المختلطة."
        )

    # ٢) نافذة المحاكاة: من البذار إلى نهاية الموسم (أو اليوم)، بحدّ أقصى.
    today = datetime.now(UTC).date()
    sow = srow["sowing_date"]
    end = srow["season_end"]
    start = sow if sow is not None else (today - timedelta(days=_SIM_MAX_WINDOW_DAYS))
    win_end = min(end, today) if end is not None else today
    if win_end <= start:
        win_end = min(start + timedelta(days=_SIM_MAX_WINDOW_DAYS), today)
    if (win_end - start).days > _SIM_MAX_WINDOW_DAYS:
        win_end = start + timedelta(days=_SIM_MAX_WINDOW_DAYS)
    # ERA5 التاريخي يتأخّر ~5 أيّام — لا نطلب أحدث من ذلك.
    win_end = min(win_end, today - timedelta(days=5))
    if win_end <= start:
        raise HTTPException(
            status_code=422,
            detail="نافذة الموسم قصيرة جدّاً أو في المستقبل — لا بيانات طقس تاريخيّة كافية للمحاكاة.",
        )

    # ٢-ب) مدخلات الموسم التاريخي من المصادر القائمة (لا نسخ ولا تخمين).
    try:
        async with tenant_connection(user) as conn:
            (
                record,
                historical_crop,
                historical_events,
                historical_harvest,
                vegetation,
            ) = await _load_linked_historical_inputs(
                conn,
                season_id,
                str(srow["field_id"]),
                user.tenant_id,
                sow,
                start,
                win_end,
            )
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة سياق الموسم التاريخي", e) from e

    # ٣) الطقس التاريخي (ERA5) من Open-Meteo — تعذّره ⇒ 503 صريح.
    try:
        days = await fetch_historical(
            float(srow["lat"]),
            float(srow["lon"]),
            start.isoformat(),
            win_end.isoformat(),
        )
    except Exception as e:  # noqa: BLE001 — تعذّر مصدر الطقس ⇒ 503 صريح
        raise HTTPException(
            status_code=503,
            detail="تعذّر جلب الطقس التاريخي (Open-Meteo غير متاح). حاول لاحقاً.",
        ) from e

    weather = [
        DayWeather(
            t_min_c=d.temp_min_c,
            t_max_c=d.temp_max_c,
            solar_mj_m2=None,  # غير مطلوب من المصدر الحالي — يُقدَّر في النموذج
            et0_mm=d.et0_mm,
            rain_mm=d.precipitation_mm or 0.0,
        )
        for d in days
    ]

    # ٣-ب) نواة GDD من محرّك الطقس (WS-C.1c Zero-Legacy) — المصدر الوحيد، لا تُحسب محلّيّاً.
    # سياسة المحصول (الأساس/السقف، method="modified") من نموذج الموسم وتُمرَّر للمحرّك؛
    # تعذّر المحرّك ⇒ 503 (لا GDD محلّيّ، لا مقارنة ظلّيّة).

    from api.season_simulation import crop_gdd_policy
    from api.weather_service_client import get_et0_series, get_gdd_product

    gdd_base, gdd_cutoff = crop_gdd_policy(crop)
    gdd_override: list[float | None] | None = None
    gdd_provenance: dict | None = None
    et0_override: list[float | None] | None = None
    et0_provenance: dict | None = None
    if weather:
        # WS-C.1b: سلسلة ET0 من محرّك الطقس (المصدر الكنسيّ) — لا Hargreaves محلّيّ في
        # المحاكاة. تعذّر المحرّك ⇒ 503 (fail-closed). خطّ عرض الحقل + يوم البدء.
        try:
            et0_series = await get_et0_series(
                daily_t_min=[w.t_min_c for w in weather],
                daily_t_max=[w.t_max_c for w in weather],
                lat_deg=float(srow["lat"]),
                day_of_year_start=start.timetuple().tm_yday,
            )
        except HTTPException as exc:
            if exc.status_code in (502, 503, 504):
                raise HTTPException(
                    status_code=503,
                    detail="weather-engine ET0 unavailable — fail-closed (no local ET0 fallback)",
                ) from exc
            raise
        et0_override = et0_series.get("daily_et0_mm")
        et0_provenance = {
            "source": "weather-engine",
            "formula_version": et0_series.get("formula_version"),
            "days_computed": et0_series.get("days_computed"),
            "accumulated_et0_mm": et0_series.get("accumulated_et0_mm"),
        }
        try:
            gdd_engine = await get_gdd_product(
                daily_t_min=[w.t_min_c for w in weather],
                daily_t_max=[w.t_max_c for w in weather],
                base_c=gdd_base,
                upper_cutoff_c=gdd_cutoff,
                method="modified",
            )
        except HTTPException as exc:
            if exc.status_code in (502, 503, 504):
                raise HTTPException(
                    status_code=503,
                    detail="weather-engine GDD unavailable — fail-closed (no local GDD fallback)",
                ) from exc
            raise
        gdd_override = gdd_engine.get("daily_gdd")
        # WS-C.1c Zero-Legacy: أُزيلت المقارنة الظلّيّة ونواة gdd_day المحلّيّة (المحرّك مصدر
        # GDD الوحيد). النَّسَب من المحرّك مباشرة.
        gdd_provenance = {
            "source": "weather-engine",
            "calculation_version": gdd_engine.get("calculation_version"),
            "thresholds_used": gdd_engine.get("thresholds_used"),
        }

    from core.historical_season_context import compose_historical_season_context

    historical_context = compose_historical_season_context(
        tenant_id=str(user.tenant_id),
        field_id=str(srow["field_id"]),
        season_id=season_id,
        season=dict(srow),
        season_record=dict(record) if record is not None else None,
        crop=dict(historical_crop) if historical_crop is not None else None,
        events=[dict(row) for row in historical_events],
        harvest=dict(historical_harvest) if historical_harvest is not None else None,
        vegetation=[dict(row) for row in vegetation],
        weather=[
            {
                "date": (start + timedelta(days=i)).isoformat(),
                "t_min_c": day.t_min_c,
                "t_max_c": day.t_max_c,
                "et0_mm": (
                    et0_override[i]
                    if et0_override is not None and i < len(et0_override)
                    else day.et0_mm
                ),
                "rain_mm": day.rain_mm,
                "gdd": (
                    gdd_override[i] if gdd_override is not None and i < len(gdd_override) else None
                ),
            }
            for i, day in enumerate(weather)
        ],
    )
    composed_inputs = historical_context["simulation_inputs"]

    # ٤) المحاكاة النقيّة (نواة GDD محقونة من المحرّك حين توفّرت).
    result = simulate_season(
        SimContext(
            crop=crop,
            sowing_date=sow,
            season_end=end,
            weather=weather,
            irrigation_mm_total=composed_inputs["irrigation_mm_total"],
            observed_fapar=composed_inputs["observed_fapar"],
            gdd_daily_override=gdd_override,
            et0_daily_override=et0_override,
        )
    )

    # ٥) حفظ النتائج على صفّ الموسم (+ وقت التشغيل).
    ran_at = datetime.now(UTC)
    import json as _json

    from api.season_simulation import ENGINE_NAME, ENGINE_VERSION, PARAMETER_VERSION

    result_payload = asdict(result)
    # Output-side companion (engine identity + prediction band + expected-vs-actual
    # delta) for the decision-center snapshot — kept out of the digested input bundle.
    from core.historical_season_context import build_simulation_outcome

    simulation_outcome = build_simulation_outcome(
        result_payload,
        engine_name=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        parameter_version=PARAMETER_VERSION,
        harvest=historical_context["manual_record"].get("harvest"),
    )
    try:
        async with tenant_connection(user) as conn:
            async with conn.transaction():
                # Insert the canonical append-only run row FIRST so its run_id can be
                # bound onto the seasons.sim_* projection in the same transaction —
                # lineage from the latest projection back to its run is never lost.
                run_id = await conn.fetchval(
                    "INSERT INTO season_simulation_runs "
                    "(tenant_id, field_id, season_id, mode, as_of_time, input_digest, "
                    "context_snapshot, engine_name, engine_version, parameter_version, "
                    "result, confidence, assumptions, warnings) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, "
                    "$11::jsonb, $12, $13::jsonb, $14::jsonb) RETURNING run_id",
                    user.tenant_id,
                    str(srow["field_id"]),
                    season_id,
                    "historical_hindcast" if record is not None else "operational",
                    datetime.combine(win_end, datetime.min.time(), tzinfo=UTC),
                    historical_context["input_digest"],
                    _json.dumps(historical_context, ensure_ascii=False, default=str),
                    ENGINE_NAME,
                    ENGINE_VERSION,
                    PARAMETER_VERSION,
                    _json.dumps(result_payload, ensure_ascii=False, default=str),
                    result.confidence,
                    _json.dumps(result.assumptions_ar, ensure_ascii=False),
                    _json.dumps(result.warnings_ar, ensure_ascii=False),
                )
                await conn.execute(
                    "UPDATE seasons SET sim_yield_kg_ha = $2, sim_biomass_kg_ha = $3, "
                    "sim_gdd_total = $4, sim_lai_max = $5, sim_water_mm = $6, "
                    "sim_ran_at = $7, sim_run_id = $8 WHERE season_id = $1",
                    season_id,
                    result.yield_kg_ha,
                    result.biomass_kg_ha,
                    result.gdd_total,
                    result.lai_max,
                    result.water_need_mm,
                    ran_at,
                    run_id,
                )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("حفظ نتائج المحاكاة", e) from e

    # ٥-ب) مرآة سياق فقط إلى مركز القرار القائم. لا قرار ولا dispatch ولا تجاوز
    # للموافقة. فشل/تعطيل SoR لا يفقد سجل التشغيل المحلي؛ الحالة تعاد صراحة.
    decision_context_status = "disabled"
    decision_historical_snapshot_id = None
    try:
        if not _decision_context_mirror_enabled():
            raise RuntimeError("decision context mirror disabled")
        from api.decision_service_client import compose_context_snapshot

        context_result = await compose_context_snapshot(
            {
                "field_id": str(srow["field_id"]),
                "season_id": season_id,
                "as_of_time": ran_at.isoformat(),
                "decision_cutoff_time": ran_at.isoformat(),
                "schema_version": "ac-1",
                "composer_version": "historical-season-bridge/1",
                "context": {
                    "crop": historical_context["manual_record"].get("crop") or {"crop": crop},
                    "soil": {"status": "missing", "reason": "not supplied by season simulation"},
                    "irrigation": {"measured_total_mm": composed_inputs["irrigation_mm_total"]},
                    "weather": {
                        "source": historical_context["weather"]["source"],
                        "day_count": historical_context["weather"]["day_count"],
                    },
                    "climate": {"status": "represented_by_historical_weather"},
                    "terrain": {"status": "not_required_for_this_simulation"},
                    "operations": {
                        "event_count": len(historical_context["manual_record"]["events"])
                    },
                    "simulation": simulation_outcome,
                },
                "historical": {
                    "history_from": datetime.combine(
                        start, datetime.min.time(), tzinfo=UTC
                    ).isoformat(),
                    "history_to": datetime.combine(
                        win_end, datetime.min.time(), tzinfo=UTC
                    ).isoformat(),
                    "manifest_version": "historical-season-context.v1",
                    "history": historical_context,
                },
                "features": [],
                "idempotency_key": f"season-sim:{run_id}",
            },
            tenant_id=str(user.tenant_id),
            requested_by=str(user.user_id),
        )
        decision_context_status = "persisted"
        decision_historical_snapshot_id = context_result.get("historical_snapshot_id")
    except HTTPException as exc:
        decision_context_status = f"unavailable:{exc.status_code}"
    except RuntimeError as exc:
        if str(exc) != "decision context mirror disabled":
            raise

    return SeasonSimResponse(
        season_id=season_id,
        crop=result.crop,
        crop_recognized=result.crop_recognized,
        days_simulated=result.days_simulated,
        gdd_total=result.gdd_total,
        gdd_to_maturity=result.gdd_to_maturity,
        maturity_reached=result.maturity_reached,
        lai_max=result.lai_max,
        biomass_kg_ha=result.biomass_kg_ha,
        yield_kg_ha=result.yield_kg_ha,
        yield_low_kg_ha=result.yield_low_kg_ha,
        yield_high_kg_ha=result.yield_high_kg_ha,
        water_need_mm=result.water_need_mm,
        water_supply_mm=result.water_supply_mm,
        water_stress_factor=result.water_stress_factor,
        confidence=result.confidence,
        rationale_ar=result.rationale_ar,
        assumptions_ar=result.assumptions_ar,
        warnings_ar=(
            [multi_crop_warning, *result.warnings_ar] if multi_crop_warning else result.warnings_ar
        ),
        sim_ran_at=ran_at.isoformat(),
        gdd_provenance=gdd_provenance,
        et0_provenance=et0_provenance,
        simulation_run_id=str(run_id),
        input_digest=historical_context["input_digest"],
        historical_context_used=record is not None,
        manual_irrigation_used=composed_inputs["irrigation_mm_total"] is not None,
        observed_fapar_used=composed_inputs["observed_fapar"] is not None,
        decision_context_status=decision_context_status,
        decision_historical_snapshot_id=decision_historical_snapshot_id,
        model_role="screening_only",
        eligible_for_calibration=False,
        simulation_engine=ENGINE_NAME,
        canonical_yield_engine="pcse_wofost",
    )


@router.get("/api/v1/fields/{field_id}/seasons/{season_id}/state")
async def field_season_state_endpoint(
    field_id: str,
    season_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """الحقيقة التشغيليّة الموحّدة للحقل-الموسم (Season Evidence) — قراءة واحدة.

    نقطة **رقيقة**: تجمع البيانات الموجودة فعلاً (صفّ الموسم + أحدث NDVI/NDMI وجودته +
    عجز الماء 7/14 يوم من water_ledger + عدد المهام المفتوحة) ثمّ تستدعي المحرّك النقيّ
    ``field_season_projection.assemble_field_season_state`` وتعيد نتيجته حرفيّاً.

    صدق: ما لا يُقرأ بسهولة الآن (accumulated_gdd، إشارات الطقس الحيّة، Ks) يُمرَّر None فيظهر
    في ``evidence_missing`` — لا رقم مُختلَق. 404 إن غاب الموسم لهذا الحقل/المستأجِر؛ القراءات
    التكميليّة best-effort (فشلها ⇒ None لا 500). 503 عند تعذّر القاعدة الأساسيّ.
    """
    import json as _json

    from api.field_season_projection import assemble_field_season_state

    def _loads(v):
        if v is None:
            return None
        return _json.loads(v) if isinstance(v, str) else v

    ndvi = ndmi = vpr = cloud = def7 = def14 = open_tasks = None
    outcome_records: list[dict] = []
    recommendation_outcomes: list[dict] = []
    dispatch_links: dict = {}
    try:
        async with tenant_connection(user) as conn:
            srow = await conn.fetchrow(
                "SELECT crops, cultivar, sowing_date, season_end FROM seasons "
                "WHERE season_id = $1 AND field_id = $2",
                season_id,
                field_id,
            )
            if srow is None:
                raise HTTPException(
                    status_code=404, detail="الموسم غير موجود لهذا الحقل ضمن هذا المستأجِر"
                )
            # أحدث مؤشّرات + جودة المشهد (best-effort).
            try:
                irow = await conn.fetchrow(
                    "SELECT ndvi_mean, ndmi_mean, valid_pixel_ratio, cloud_pct "
                    "FROM imagery_automation_fields WHERE field_id = $1 "
                    "ORDER BY acquisition_date DESC NULLS LAST LIMIT 1",
                    field_id,
                )
                if irow is not None:
                    ndvi, ndmi = irow["ndvi_mean"], irow["ndmi_mean"]
                    vpr, cloud = irow["valid_pixel_ratio"], irow["cloud_pct"]
            except Exception:  # noqa: BLE001 — تكميليّ: الغياب ⇒ evidence_missing لا 500
                pass
            # عجز الماء التراكميّ 7/14 يوم من دفتر المياه (best-effort).
            try:
                wrow = await conn.fetchrow(
                    "SELECT SUM(deficit_mm) FILTER "
                    "(WHERE ledger_date >= CURRENT_DATE - INTERVAL '7 days')  AS d7, "
                    "SUM(deficit_mm) FILTER "
                    "(WHERE ledger_date >= CURRENT_DATE - INTERVAL '14 days') AS d14 "
                    "FROM water_ledger WHERE field_id = $1",
                    field_id,
                )
                if wrow is not None:
                    def7 = float(wrow["d7"]) if wrow["d7"] is not None else None
                    def14 = float(wrow["d14"]) if wrow["d14"] is not None else None
            except Exception:  # noqa: BLE001
                pass
            # عدد المهام المفتوحة (best-effort).
            try:
                cnt = await conn.fetchval(
                    "SELECT COUNT(*) FROM field_tasks WHERE field_id = $1 "
                    "AND status NOT IN ('done', 'completed', 'cancelled')",
                    field_id,
                )
                open_tasks = int(cnt) if cnt is not None else None
            except Exception:  # noqa: BLE001
                pass
            # النتائج المتصالحة (best-effort): outcome_record + recommendation_outcomes.
            # الغياب/الجداول الجزئية لا يعطل حقيقة الموسم؛ يظهر outcomes ضمن evidence_missing.
            try:
                rows = await conn.fetch(
                    "SELECT outcome_id, field_id, region, decision_id, success, metrics, "
                    "planned, actual, stage, created_at FROM outcome_record "
                    "WHERE field_id = $1",
                    field_id,
                )
                outcome_records = [
                    {
                        "outcome_id": r["outcome_id"],
                        "field_id": r["field_id"],
                        "region": r["region"],
                        "decision_id": r["decision_id"],
                        "success": r["success"],
                        "metrics": _loads(r["metrics"]) or {},
                        "planned": _loads(r["planned"]),
                        "actual": _loads(r["actual"]),
                        "stage": r["stage"],
                        "created_at": r["created_at"],
                    }
                    for r in rows
                ]
            except Exception:  # noqa: BLE001
                outcome_records = []
            try:
                rows = await conn.fetch(
                    "SELECT outcome_id, field_id, season_id, crop, recommendation_id, "
                    "predicted_yield_t_ha, actual_yield_t_ha, accepted, matured_within_lag, "
                    "issued_at, outcome_recorded_at FROM recommendation_outcomes "
                    "WHERE field_id = $1 AND (season_id = $2 OR season_id IS NULL)",
                    field_id,
                    season_id,
                )
                recommendation_outcomes = [
                    {
                        "outcome_id": r["outcome_id"],
                        "field_id": r["field_id"],
                        "season_id": r["season_id"],
                        "crop": r["crop"],
                        "recommendation_id": r["recommendation_id"],
                        "predicted_yield_t_ha": r["predicted_yield_t_ha"],
                        "actual_yield_t_ha": r["actual_yield_t_ha"],
                        "accepted": r["accepted"],
                        "matured_within_lag": r["matured_within_lag"],
                        "issued_at": r["issued_at"],
                        "outcome_recorded_at": r["outcome_recorded_at"],
                    }
                    for r in rows
                ]
            except Exception:  # noqa: BLE001
                recommendation_outcomes = []
            try:
                rows = await conn.fetch(
                    "SELECT recommendation_id, decision_id FROM dispatch_decisions"
                )
                dispatch_links = {
                    r["recommendation_id"]: r["decision_id"]
                    for r in rows
                    if r["recommendation_id"] and r["decision_id"]
                }
            except Exception:  # noqa: BLE001
                dispatch_links = {}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — تعذّر القاعدة الأساسيّ ⇒ 503 موثَّق
        raise _db_unavailable("قراءة حالة الحقل-الموسم", e) from e

    crops = srow["crops"]
    if isinstance(crops, str):
        try:
            crops = _json.loads(crops)
        except (ValueError, TypeError):
            crops = []
    first_crop = str(crops[0]) if isinstance(crops, list) and crops else None

    return assemble_field_season_state(
        field_id=field_id,
        season_id=season_id,
        crop=first_crop,
        cultivar=srow["cultivar"],
        sowing_date=srow["sowing_date"],
        season_end=srow["season_end"],
        observed_ndvi=ndvi,
        observed_ndmi=ndmi,
        valid_pixel_ratio=vpr,
        cloud_pct=cloud,
        water_deficit_7d_mm=def7,
        water_deficit_14d_mm=def14,
        open_tasks_count=open_tasks,
        outcome_records=outcome_records,
        recommendation_outcomes=recommendation_outcomes,
        dispatch_links=dispatch_links,
    )
