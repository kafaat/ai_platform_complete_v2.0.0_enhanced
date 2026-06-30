"""Field AI Context Pack — 2-year field memory for AI chat.

This router assembles a bounded, tenant-scoped context packet for the AI advisor.
It does not invent agronomic facts: every optional source reports whether it was
available, and partial failures are returned in `readiness.warnings` instead of
breaking the chat UI.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from statistics import mean
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.main import Permission, UserSchema, require_permission, tenant_connection

router = APIRouter(tags=["field-ai-context"])


class FieldAiContextPack(BaseModel):
    field_id: str
    tenant_id: str
    days: int
    generated_at: str
    field_profile: dict[str, Any] = Field(default_factory=dict)
    active_season: dict[str, Any] | None = None
    imagery_timeline: dict[str, Any] = Field(default_factory=dict)
    weather_history: dict[str, Any] = Field(default_factory=dict)
    operations_timeline: dict[str, Any] = Field(default_factory=dict)
    drawing_context: dict[str, Any] = Field(default_factory=dict)
    alerts_context: dict[str, Any] = Field(default_factory=dict)
    recommendations_context: dict[str, Any] = Field(default_factory=dict)
    ai_context_summary_ar: str
    readiness: dict[str, Any] = Field(default_factory=dict)


def _as_json(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value


def _record_to_json(row: Any, key: str = "payload") -> Any:
    if row is None:
        return None
    value = row[key]
    return _as_json(value, value)


def _normalise_row_dict(value: Any) -> dict[str, Any]:
    value = _as_json(value, value)
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in value.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _collect_positions(coords: Any, out: list[tuple[float, float]]) -> None:
    if not isinstance(coords, list):
        return
    if len(coords) >= 2 and all(isinstance(v, (int, float)) for v in coords[:2]):
        lon, lat = float(coords[0]), float(coords[1])
        if -180 <= lon <= 180 and -90 <= lat <= 90:
            out.append((lon, lat))
        return
    for child in coords:
        _collect_positions(child, out)


def _centroid_from_geojson(geometry: Any) -> dict[str, float] | None:
    geometry = _as_json(geometry, geometry)
    if not isinstance(geometry, dict):
        return None
    pts: list[tuple[float, float]] = []
    _collect_positions(geometry.get("coordinates"), pts)
    if not pts:
        return None
    lon = sum(p[0] for p in pts) / len(pts)
    lat = sum(p[1] for p in pts) / len(pts)
    return {"lat": round(lat, 6), "lon": round(lon, 6)}


async def _fetch_field_profile(
    conn, field_id: str, tenant_id: str
) -> tuple[dict[str, Any], dict[str, float] | None]:
    row = await conn.fetchrow(
        "SELECT to_jsonb(f.*) AS payload FROM fields f WHERE f.field_id = $1 AND f.tenant_id = $2::uuid LIMIT 1",
        field_id,
        tenant_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
    profile = _normalise_row_dict(row["payload"])
    centroid = _centroid_from_geojson(profile.get("geometry") or profile.get("geom"))
    return profile, centroid


async def _optional_active_season(
    conn, field_id: str, tenant_id: str
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        row = await conn.fetchrow(
            """
            SELECT to_jsonb(s.*) AS payload
            FROM seasons s
            WHERE s.field_id = $1 AND s.tenant_id = $2::uuid
              AND COALESCE(s.status, 'active') IN ('active', 'current', 'in_progress')
            ORDER BY COALESCE(s.started_at, s.start_date, s.created_at) DESC NULLS LAST
            LIMIT 1
            """,
            field_id,
            tenant_id,
        )
        return (_normalise_row_dict(row["payload"]) if row else None), None
    except Exception as exc:  # noqa: BLE001
        return None, f"تعذّر جلب الموسم النشط: {exc}"


async def _optional_events(conn, field_id: str, limit: int) -> tuple[dict[str, Any], str | None]:
    try:
        rows = await conn.fetch(
            """
            SELECT event_id, event_type, payload, actor_id, occurred_at
            FROM events
            WHERE entity_id = $1 OR payload->>'field_id' = $1
            ORDER BY occurred_at DESC
            LIMIT $2
            """,
            field_id,
            max(1, min(limit, 500)),
        )
        events = [
            {
                "event_id": str(r["event_id"]),
                "event_type": r["event_type"],
                "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else None,
                "actor_id": r["actor_id"],
                "payload": _as_json(r["payload"], {}) or {},
            }
            for r in rows
        ]
        return {"available": True, "events": events, "total": len(events)}, None
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "events": [], "total": 0}, f"تعذّر جلب timeline الأحداث: {exc}"


async def _optional_drawings(
    conn, field_id: str, tenant_id: str
) -> tuple[dict[str, Any], str | None]:
    try:
        rows = await conn.fetch(
            """
            SELECT feature_id, kind, workflow, properties, measurements, validation, version, updated_at
            FROM drawing_features
            WHERE tenant_id = $1::uuid AND field_id = $2 AND deleted_at IS NULL
            ORDER BY updated_at DESC
            LIMIT 200
            """,
            tenant_id,
            field_id,
        )
        features = [
            {
                "id": r["feature_id"],
                "kind": r["kind"],
                "workflow": r["workflow"],
                "properties": _as_json(r["properties"], {}) or {},
                "measurements": _as_json(r["measurements"], {}) or {},
                "validation": _as_json(r["validation"], {}) or {},
                "version": r["version"],
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            }
            for r in rows
        ]
        by_kind: dict[str, int] = {}
        for item in features:
            by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1
        return {
            "available": True,
            "features": features,
            "counts_by_kind": by_kind,
            "total": len(features),
        }, None
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "features": [],
            "counts_by_kind": {},
            "total": 0,
        }, f"تعذّر جلب هندسات الرسم: {exc}"


async def _optional_alerts(
    conn, field_id: str, tenant_id: str
) -> tuple[dict[str, Any], str | None]:
    try:
        rows = await conn.fetch(
            """
            SELECT to_jsonb(a.*) AS payload
            FROM alerts a
            WHERE a.tenant_id = $1::uuid AND (a.field_id = $2 OR a.payload->>'field_id' = $2)
            ORDER BY COALESCE(a.created_at, a.updated_at) DESC NULLS LAST
            LIMIT 50
            """,
            tenant_id,
            field_id,
        )
        alerts = [_normalise_row_dict(r["payload"]) for r in rows]
        return {"available": True, "items": alerts, "total": len(alerts)}, None
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "items": [], "total": 0}, f"تعذّر جلب التنبيهات: {exc}"


async def _optional_recommendations(
    conn, field_id: str, tenant_id: str
) -> tuple[dict[str, Any], str | None]:
    try:
        rows = await conn.fetch(
            """
            SELECT to_jsonb(r.*) AS payload
            FROM recommendations r
            WHERE r.tenant_id = $1::uuid AND (r.field_id = $2 OR r.payload->>'field_id' = $2)
            ORDER BY COALESCE(r.created_at, r.updated_at) DESC NULLS LAST
            LIMIT 50
            """,
            tenant_id,
            field_id,
        )
        recommendations = [_normalise_row_dict(r["payload"]) for r in rows]
        return {"available": True, "items": recommendations, "total": len(recommendations)}, None
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "items": [], "total": 0}, f"تعذّر جلب التوصيات: {exc}"


async def _optional_imagery_timeline(
    field_id: str, tenant_id: str, days: int
) -> tuple[dict[str, Any], str | None]:
    raster_url = os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8001").rstrip("/")
    headers = {"X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", ""), "X-Tenant-Id": tenant_id}
    since = date.today() - timedelta(days=days)
    indicators = ["truecolor", "ndvi", "ndmi", "ndre", "msavi"]
    per_indicator: dict[str, Any] = {}
    warnings: list[str] = []
    async with httpx.AsyncClient(timeout=12.0) as client:
        for indicator in indicators:
            try:
                resp = await client.get(
                    f"{raster_url}/v1/fields/{field_id}/available-dates",
                    params={"index": indicator},
                    headers=headers,
                )
                resp.raise_for_status()
                payload = resp.json()
                dates = payload.get("dates") if isinstance(payload, dict) else payload
                if not isinstance(dates, list):
                    dates = []
                filtered = []
                for item in dates:
                    d = item.get("date") if isinstance(item, dict) else str(item)
                    if d and d[:10] >= since.isoformat():
                        filtered.append(item)
                per_indicator[indicator] = {
                    "available": True,
                    "dates": filtered,
                    "total": len(filtered),
                }
            except Exception as exc:  # noqa: BLE001
                per_indicator[indicator] = {"available": False, "dates": [], "total": 0}
                warnings.append(f"{indicator}: {exc}")
    total_dates = sum(int(v.get("total", 0)) for v in per_indicator.values())
    return {
        "available": total_dates > 0,
        "range_days": days,
        "since": since.isoformat(),
        "until": date.today().isoformat(),
        "per_indicator": per_indicator,
        "total_dates": total_dates,
        "note_ar": "يعرض فقط المشاهد الموجودة/المجهزة؛ استخدم imagery/backfill custom months=24 لتجهيز سنتين.",
    }, ("؛ ".join(warnings) if warnings else None)


async def _optional_weather_history(
    centroid: dict[str, float] | None, days: int
) -> tuple[dict[str, Any], str | None]:
    if not centroid:
        return {
            "available": False,
            "days": [],
            "summary": {},
        }, "لا توجد إحداثيات صالحة للحقل لجلب الطقس التاريخي."
    end = date.today()
    start = end - timedelta(days=days)
    try:
        from api.connectors.openmeteo import fetch_historical

        records = await fetch_historical(
            centroid["lat"], centroid["lon"], start.isoformat(), end.isoformat()
        )
        if not records:
            return {
                "available": False,
                "range": {"start": start.isoformat(), "end": end.isoformat()},
                "days": [],
                "summary": {},
            }, None
        temp_vals = [
            ((d.temp_max_c or 0) + (d.temp_min_c or 0)) / 2
            for d in records
            if d.temp_max_c is not None and d.temp_min_c is not None
        ]
        precip_vals = [float(d.precipitation_mm or 0) for d in records]
        et0_vals = [float(d.et0_mm or 0) for d in records]
        summary = {
            "days": len(records),
            "avg_temp_c": round(mean(temp_vals), 2) if temp_vals else None,
            "total_precipitation_mm": round(sum(precip_vals), 2),
            "total_et0_mm": round(sum(et0_vals), 2),
            "first_date": records[0].date,
            "last_date": records[-1].date,
        }
        # Keep context compact for the chat runtime: monthly buckets by YYYY-MM.
        monthly: dict[str, dict[str, Any]] = {}
        for d in records:
            key = str(d.date)[:7]
            b = monthly.setdefault(key, {"days": 0, "precipitation_mm": 0.0, "et0_mm": 0.0})
            b["days"] += 1
            b["precipitation_mm"] += float(d.precipitation_mm or 0)
            b["et0_mm"] += float(d.et0_mm or 0)
        monthly_items = [
            {
                "month": k,
                "days": v["days"],
                "precipitation_mm": round(v["precipitation_mm"], 2),
                "et0_mm": round(v["et0_mm"], 2),
            }
            for k, v in sorted(monthly.items())
        ]
        return {
            "available": True,
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "location": centroid,
            "summary": summary,
            "monthly": monthly_items,
            "source": "open-meteo-archive",
        }, None
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "summary": {},
        }, f"تعذّر جلب طقس سنتين: {exc}"


def _summary_ar(pack: dict[str, Any]) -> str:
    field = pack.get("field_profile") or {}
    imagery = pack.get("imagery_timeline") or {}
    weather = pack.get("weather_history") or {}
    drawings = pack.get("drawing_context") or {}
    events = pack.get("operations_timeline") or {}
    name = field.get("name") or field.get("field_name") or pack.get("field_id")
    parts = [
        f"سياق الحقل {name}:",
        f"نطاق الذاكرة {pack.get('days')} يوم.",
        f"مشاهد الأقمار المتاحة: {imagery.get('total_dates', 0)}.",
        f"أحداث timeline: {events.get('total', 0)}.",
        f"هندسات ومناطق محفوظة: {drawings.get('total', 0)}.",
    ]
    if weather.get("available"):
        s = weather.get("summary") or {}
        parts.append(
            f"طقس تاريخي: {s.get('days')} يوم، مطر تراكمي {s.get('total_precipitation_mm')} مم، ET0 {s.get('total_et0_mm')} مم."
        )
    else:
        parts.append("الطقس التاريخي غير متاح لهذا الحقل حالياً.")
    return " ".join(parts)


@router.get("/api/v1/fields/{field_id}/ai-context-pack", response_model=FieldAiContextPack)
async def field_ai_context_pack(
    field_id: str,
    days: int = Query(730, ge=30, le=1825),
    include_weather: bool = True,
    include_imagery: bool = True,
    include_events: bool = True,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """Return a compact 2-year context packet for the AI advisor.

    The response is designed to be injected into `/api/ai-agronomist/chat` under
    `current_field_state.ai_context_pack`, so the model sees the same field,
    imagery dates, historical weather summary, events, alerts, drawings, and
    recommendations that the UI displays.
    """
    warnings: list[str] = []
    async with tenant_connection(user) as conn:
        field_profile, centroid = await _fetch_field_profile(conn, field_id, str(user.tenant_id))
        active_season, warn = await _optional_active_season(conn, field_id, str(user.tenant_id))
        if warn:
            warnings.append(warn)

        operations = {"available": False, "events": [], "total": 0}
        if include_events:
            operations, warn = await _optional_events(conn, field_id, 300)
            if warn:
                warnings.append(warn)

        drawings, warn = await _optional_drawings(conn, field_id, str(user.tenant_id))
        if warn:
            warnings.append(warn)

        alerts, warn = await _optional_alerts(conn, field_id, str(user.tenant_id))
        if warn:
            warnings.append(warn)

        recommendations, warn = await _optional_recommendations(conn, field_id, str(user.tenant_id))
        if warn:
            warnings.append(warn)

    imagery = {"available": False, "per_indicator": {}, "total_dates": 0}
    if include_imagery:
        imagery, warn = await _optional_imagery_timeline(field_id, str(user.tenant_id), days)
        if warn:
            warnings.append(f"imagery timeline جزئي: {warn}")

    weather = {"available": False, "summary": {}}
    if include_weather:
        weather, warn = await _optional_weather_history(centroid, days)
        if warn:
            warnings.append(warn)

    payload: dict[str, Any] = {
        "field_id": field_id,
        "tenant_id": str(user.tenant_id),
        "days": days,
        "generated_at": datetime.now(UTC).isoformat(),
        "field_profile": field_profile,
        "active_season": active_season,
        "imagery_timeline": imagery,
        "weather_history": weather,
        "operations_timeline": operations,
        "drawing_context": drawings,
        "alerts_context": alerts,
        "recommendations_context": recommendations,
        "readiness": {
            "complete": not warnings,
            "warnings": warnings,
            "requires_imagery_backfill_24_months": int(imagery.get("total_dates", 0) or 0) == 0,
            "weather_history_available": bool(weather.get("available")),
        },
    }
    payload["ai_context_summary_ar"] = _summary_ar(payload)
    return FieldAiContextPack(**payload)
