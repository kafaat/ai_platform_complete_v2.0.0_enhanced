"""api/routers/agronomic_replay.py — إعادة تشغيل الموسم لحقل (قراءة فقط، #4/D)

نقطة واحدة محروسة بعلم ``FEATURE_REPLAY_MAP`` (مُطفأة افتراضاً ⇒ 404):

  • ``GET /api/v1/fields/{field_id}/agronomic-replay`` — يجمع سلاسل الحقل المُدامة
    (NDVI، ريّ، قرارات، نتائج) في **خطّ زمنيّ واحد مرتّب** لإعادة تشغيل الموسم
    (scrub)، عبر ``tenant_connection`` (عزل RLS).

**الصدق**: كل مصدر يعيد حالة صريحة؛ لا تساوي المنصة بين البيانات الفارغة والمصدر
غير المتاح. NDVI يُقرأ من raster-service القانونيّ (لا جدول ``ndvi_timeseries`` الميّت)
عبر الواجهة المسموح بها؛ الطقس يُقرأ أولاً من لقطة تشغيل المحاكاة، ثم من مصدر حقيقة
الطقس التاريخي القانوني مع احترام وقت الإتاحة.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from api.agronomic_replay import build_agronomic_replay
from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}
_PER_TRACK_LIMIT = 300  # سقف لكلّ مسار (خطّ زمنيّ لا تفريغ كامل)


def _replay_map_enabled() -> bool:
    """هل ميزة إعادة تشغيل الموسم مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ)."""
    return os.getenv("FEATURE_REPLAY_MAP", "").strip().lower() in _TRUTHY


async def _rows(conn, sql: str, *args) -> tuple[list[dict], str]:
    """Fetch one source without hiding an unavailable schema/permission as empty."""
    try:
        res = await conn.fetch(sql, *args)
    except Exception:  # noqa: BLE001 — مصدر غائب ⇒ مسار فارغ
        return [], "unavailable"
    rows = [dict(r) for r in res]
    return rows, ("available" if rows else "empty")


def _source(status: str, rows: list[dict], source: str, quality: str) -> dict:
    return {"status": status, "count": len(rows), "source": source, "quality": quality}


@router.get("/api/v1/fields/{field_id}/agronomic-replay")
async def agronomic_replay_endpoint(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """خطّ زمنيّ موحّد لإعادة تشغيل موسم الحقل (RLS) — قراءة فقط. 404 إن مُطفأ، 503 إن تعذّرت القاعدة.

    يجمع NDVI/ريّ/قرارات/نتائج الحقل المُدامة (كلّ مسار best-effort) ثمّ يدمجها عبر
    الطبقة النقيّة ``build_agronomic_replay`` في أحداث مرتّبة تصاعديّاً. غياب مسار ⇒ صفر
    صريح لا تلفيق.
    """
    if not _replay_map_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة إعادة تشغيل الموسم غير مُفعَّلة (اضبط FEATURE_REPLAY_MAP).",
        )
    # Canonical NDVI track: the scalar per-date index mean from raster-service (live
    # from the field's clipped COGs) via the allowlisted HTTP facade — NOT the legacy
    # ``ndvi_timeseries`` table (seed-only, no live writer). Fail-soft: any failure ⇒
    # empty NDVI track, never a 503 and never fabricated. Cap to the most-recent
    # per-track limit; the pure builder re-sorts ascending.
    from api.raster_service_client import (
        get_field_timeseries,
        timeseries_point_to_vegetation_row,
    )

    ndvi_points = await get_field_timeseries(field_id, tenant_id=user.tenant_id, index="ndvi")
    ndvi_points.sort(key=lambda p: str(p.get("datetime") or ""), reverse=True)
    ndvi = [
        timeseries_point_to_vegetation_row(point, field_id=field_id)
        for point in ndvi_points[:_PER_TRACK_LIMIT]
    ]
    # Fail-soft facade collapses transport errors to []; the honest status we can
    # report is available/empty (the endpoint itself dropped no-COG dates already).
    ndvi_status = "available" if ndvi else "empty"

    try:
        async with tenant_connection(user) as conn:
            irrigation, irrigation_status = await _rows(
                conn,
                "SELECT schedule_id, name, last_run_at, water_target_mm FROM irrigation_schedules "
                f"WHERE field_id = $1 AND last_run_at IS NOT NULL ORDER BY last_run_at DESC LIMIT {_PER_TRACK_LIMIT}",
                field_id,
            )
            decisions, decision_status = await _rows(
                conn,
                "SELECT decision_id, decision_type, confidence, created_at FROM decision_record "
                f"WHERE field_id = $1 ORDER BY created_at DESC LIMIT {_PER_TRACK_LIMIT}",
                field_id,
            )
            outcomes, outcome_status = await _rows(
                conn,
                "SELECT outcome_id, decision_id, success, created_at FROM outcome_record "
                f"WHERE field_id = $1 ORDER BY created_at DESC LIMIT {_PER_TRACK_LIMIT}",
                field_id,
            )
            manual_irrigation, manual_irrigation_status = await _rows(
                conn,
                "SELECT e.id AS schedule_id, e.event_date AS date, "
                "'ريّ من دفتر موسم معتمد' AS name, e.amount_mm AS water_target_mm "
                "FROM season_record_links l "
                "JOIN season_records sr ON sr.id = l.season_record_id "
                "JOIN season_events e ON e.season_id = sr.id "
                "WHERE l.field_id = $1 AND sr.trust_status = 'accepted' "
                "AND e.event_type = 'irrigation' "
                "AND NOT EXISTS (SELECT 1 FROM season_record_links n "
                "                WHERE n.supersedes_link_id = l.link_id) "
                f"ORDER BY e.event_date DESC LIMIT {_PER_TRACK_LIMIT}",
                field_id,
            )
            manual_harvests, manual_harvest_status = await _rows(
                conn,
                "SELECT h.season_id AS ref_id, h.harvest_date AS date, "
                "'حصاد من دفتر موسم معتمد' AS label_ar, h.yield_kg_ha AS value "
                "FROM season_record_links l "
                "JOIN season_records sr ON sr.id = l.season_record_id "
                "JOIN season_harvest h ON h.season_id = sr.id "
                "WHERE l.field_id = $1 AND sr.trust_status = 'accepted' "
                "AND NOT EXISTS (SELECT 1 FROM season_record_links n "
                "                WHERE n.supersedes_link_id = l.link_id) "
                f"ORDER BY h.harvest_date DESC LIMIT {_PER_TRACK_LIMIT}",
                field_id,
            )
            simulation_context_rows, simulation_status = await _rows(
                conn,
                "SELECT context_snapshot FROM season_simulation_runs "
                "WHERE field_id = $1 ORDER BY created_at DESC LIMIT 1",
                field_id,
            )
            canonical_weather, canonical_weather_status = await _rows(
                conn,
                "SELECT observed_on AS date, payload, quality, source, available_at "
                "FROM historical_weather_daily "
                "WHERE field_id = $1 AND available_at <= now() "
                "AND NOT EXISTS (SELECT 1 FROM historical_weather_daily newer "
                "                WHERE newer.supersedes_record_id = historical_weather_daily.record_id) "
                f"ORDER BY observed_on ASC, available_at DESC LIMIT {_PER_TRACK_LIMIT}",
                field_id,
            )
    except Exception as e:  # noqa: BLE001 — تعذّر فتح اتّصال المستأجِر ⇒ 503 موثَّق
        raise _db_unavailable("إعادة تشغيل الموسم", e) from e

    weather: list[dict] = []
    if simulation_context_rows:
        snapshot = simulation_context_rows[0].get("context_snapshot")
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except (TypeError, ValueError):
                snapshot = {}
        if isinstance(snapshot, dict):
            weather_group = snapshot.get("weather")
            if isinstance(weather_group, dict) and isinstance(weather_group.get("days"), list):
                weather = [row for row in weather_group["days"] if isinstance(row, dict)]
    weather_status = "available" if weather else simulation_status
    weather_source = "season_simulation_runs.context_snapshot"
    if not weather and canonical_weather:
        weather = [
            {
                "date": row.get("date"),
                **(row.get("payload") if isinstance(row.get("payload"), dict) else {}),
            }
            for row in canonical_weather
        ]
        weather_status = canonical_weather_status
        weather_source = "historical_weather_daily"
    elif not weather and simulation_status == "empty":
        weather_status = canonical_weather_status
        weather_source = "historical_weather_daily"

    out = build_agronomic_replay(
        field_id,
        ndvi=ndvi,
        weather=weather,
        irrigation=[*irrigation, *manual_irrigation],
        decisions=decisions,
        outcomes=[*outcomes, *manual_harvests],
        generated_at=datetime.now(UTC).isoformat(),
    )
    manual_rows = [*manual_irrigation, *manual_harvests]
    manual_status = (
        "available"
        if manual_rows
        else "unavailable"
        if "unavailable" in {manual_irrigation_status, manual_harvest_status}
        else "empty"
    )
    out["source_status"] = {
        "ndvi": _source(
            ndvi_status, ndvi, "raster-service:/v1/fields/{id}/timeseries", "live_cog_mean"
        ),
        "weather": _source(weather_status, weather, weather_source, "point_in_time"),
        "irrigation": _source(
            "available" if irrigation or manual_irrigation else irrigation_status,
            [*irrigation, *manual_irrigation],
            "irrigation_schedules+accepted_season_events",
            "mixed",
        ),
        "decision": _source(decision_status, decisions, "decision_record", "canonical"),
        "outcome": _source(
            "available" if outcomes or manual_harvests else outcome_status,
            [*outcomes, *manual_harvests],
            "outcome_record+accepted_season_harvest",
            "mixed",
        ),
        "manual_logbook": _source(
            manual_status, manual_rows, "accepted_season_records", "accepted_only"
        ),
    }
    out["tenant_id"] = str(user.tenant_id)  # أثر: لِمن هذه الإعادة (RLS)
    return out
