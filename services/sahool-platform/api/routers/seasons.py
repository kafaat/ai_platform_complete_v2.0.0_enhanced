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

    # ٣-ب) نواة GDD من محرّك الطقس (WS-C.1c) — المصدر الكنسيّ، لا تُحسب محلّيّاً.
    # سياسة المحصول (الأساس/السقف، method="modified") من نموذج الموسم وتُمرَّر للمحرّك؛
    # تعذّر المحرّك ⇒ 503 (لا GDD محلّيّ). مقارنة ظلّيّة (modified↔modified ⇒ match).
    import logging as _logging

    from api.gdd_shadow import compare_gdd_shadow
    from api.season_simulation import crop_gdd_policy, gdd_day
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
        legacy_daily = [gdd_day(w.t_min_c, w.t_max_c, gdd_base, gdd_cutoff) for w in weather]
        shadow = compare_gdd_shadow(
            legacy_daily=legacy_daily,
            legacy_accumulated=round(sum(legacy_daily), 3),
            legacy_method="modified",
            legacy_base_c=gdd_base,
            legacy_upper_cutoff_c=gdd_cutoff,
            engine_product=gdd_engine,
        )
        _logging.getLogger("sahool.gdd.shadow").info(
            "gdd_shadow consumer=season_simulation season=%s status=%s acc_diff=%s",
            season_id,
            shadow["shadow_status"],
            shadow["accumulated_diff"],
        )
        gdd_provenance = {
            "source": "weather-engine",
            "calculation_version": gdd_engine.get("calculation_version"),
            "thresholds_used": gdd_engine.get("thresholds_used"),
            "shadow": shadow,
        }

    # ٤) المحاكاة النقيّة (نواة GDD محقونة من المحرّك حين توفّرت).
    result = simulate_season(
        SimContext(
            crop=crop,
            sowing_date=sow,
            season_end=end,
            weather=weather,
            gdd_daily_override=gdd_override,
            et0_daily_override=et0_override,
        )
    )

    # ٥) حفظ النتائج على صفّ الموسم (+ وقت التشغيل).
    ran_at = datetime.now(UTC)
    try:
        async with tenant_connection(user) as conn:
            await conn.execute(
                "UPDATE seasons SET sim_yield_kg_ha = $2, sim_biomass_kg_ha = $3, "
                "sim_gdd_total = $4, sim_lai_max = $5, sim_water_mm = $6, sim_ran_at = $7 "
                "WHERE season_id = $1",
                season_id,
                result.yield_kg_ha,
                result.biomass_kg_ha,
                result.gdd_total,
                result.lai_max,
                result.water_need_mm,
                ran_at,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("حفظ نتائج المحاكاة", e) from e

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
