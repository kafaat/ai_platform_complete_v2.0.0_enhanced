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


# v49.5 hardening: keep the AI context compact, tenant-scoped, and safe to pass to an LLM.
_CONTEXT_MAX_ITEMS = {
    "events": 120,
    "drawings": 80,
    "alerts": 40,
    "recommendations": 40,
}
_CONTEXT_MAX_BYTES = 36_000
_REDACT_KEYS = {
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "email",
    "phone",
    "mobile",
    "sms_number",
    "whatsapp_number",
    "owner_name",
    "registry_no",
    "national_id",
    "file_url",
    "signed_url",
    "url",
}


def _is_sensitive_key(key: Any) -> bool:
    k = str(key).lower()
    return any(marker in k for marker in _REDACT_KEYS)


def _redact_value(key: Any, value: Any) -> Any:
    if _is_sensitive_key(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): _redact_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value[:50]]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "…[truncated]"
    return value


def _redact_context(value: Any) -> Any:
    return _redact_value("", value)


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except Exception:  # noqa: BLE001
        return 0


def _budget_list(
    items: list[dict[str, Any]], *, max_items: int
) -> tuple[list[dict[str, Any]], int]:
    trimmed = items[: max(0, max_items)]
    return trimmed, max(0, len(items) - len(trimmed))


def _source_provenance(
    source: str,
    status: str,
    *,
    table: str | None = None,
    service: str | None = None,
    total: int | None = None,
    confidence: float | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "table": table,
        "service": service,
        "status": status,
        "total": total,
        "confidence": confidence,
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
    }


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if hasattr(value, "isoformat"):
        value = value.isoformat()
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _freshness_score(items: list[dict[str, Any]], date_keys: tuple[str, ...]) -> float | None:
    latest: datetime | None = None
    for item in items:
        for key in date_keys:
            dt = _parse_dt(item.get(key))
            if dt and (latest is None or dt > latest):
                latest = dt
    if latest is None:
        return None
    age_days = max(0.0, (datetime.now(UTC) - latest.astimezone(UTC)).total_seconds() / 86400.0)
    if age_days <= 7:
        return 1.0
    if age_days >= 730:
        return 0.0
    return round(max(0.0, 1.0 - (age_days / 730.0)), 3)


def _apply_final_context_budget(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    warnings: list[str] = []
    budget = {
        "max_bytes": _CONTEXT_MAX_BYTES,
        "actual_bytes_before_final_trim": _json_size(payload),
        "trimmed": False,
    }
    # Field profile is useful but can contain long/free-text or PII-like attributes.
    payload["field_profile"] = _redact_context(payload.get("field_profile") or {})
    payload["active_season"] = (
        _redact_context(payload.get("active_season")) if payload.get("active_season") else None
    )
    for section in (
        "operations_timeline",
        "drawing_context",
        "alerts_context",
        "recommendations_context",
    ):
        payload[section] = _redact_context(payload.get(section) or {})
    if _json_size(payload) > _CONTEXT_MAX_BYTES:
        budget["trimmed"] = True
        warnings.append("تم تقليص سياق AI لأنه تجاوز ميزانية الحجم الآمنة.")
        # Last-resort compaction: keep summaries/counts/provenance, drop bulky lists.
        for section, key in (
            ("operations_timeline", "events"),
            ("drawing_context", "features"),
            ("alerts_context", "items"),
            ("recommendations_context", "items"),
        ):
            block = payload.get(section)
            if isinstance(block, dict) and key in block:
                block[f"{key}_omitted_by_budget"] = len(block.get(key) or [])
                block[key] = []
    budget["actual_bytes_after_final_trim"] = _json_size(payload)
    return payload, budget, warnings


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


async def _optional_events(
    conn, field_id: str, tenant_id: str, limit: int
) -> tuple[dict[str, Any], str | None]:
    try:
        rows = await conn.fetch(
            """
            SELECT event_id, event_type, payload, actor_id, occurred_at
            FROM events
            WHERE tenant_id = $2::uuid
              AND (entity_id = $1 OR payload->>'field_id' = $1)
            ORDER BY occurred_at DESC
            LIMIT $3
            """,
            field_id,
            tenant_id,
            max(1, min(limit, _CONTEXT_MAX_ITEMS["events"])),
        )
        raw_events = [
            {
                "event_id": str(r["event_id"]),
                "event_type": r["event_type"],
                "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else None,
                "actor_id": r["actor_id"],
                "payload": _redact_context(_as_json(r["payload"], {}) or {}),
            }
            for r in rows
        ]
        events, omitted = _budget_list(raw_events, max_items=_CONTEXT_MAX_ITEMS["events"])
        return {
            "available": True,
            "events": events,
            "total": len(raw_events),
            "omitted_by_budget": omitted,
            "freshness_score": _freshness_score(events, ("occurred_at",)),
            "provenance": [
                _source_provenance("events", "available", table="events", total=len(raw_events))
            ],
        }, None
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
        raw_features = [
            {
                "id": r["feature_id"],
                "kind": r["kind"],
                "workflow": r["workflow"],
                "properties": _redact_context(_as_json(r["properties"], {}) or {}),
                "measurements": _redact_context(_as_json(r["measurements"], {}) or {}),
                "validation": _redact_context(_as_json(r["validation"], {}) or {}),
                "version": r["version"],
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            }
            for r in rows
        ]
        features, omitted = _budget_list(raw_features, max_items=_CONTEXT_MAX_ITEMS["drawings"])
        by_kind: dict[str, int] = {}
        for item in features:
            by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1
        return {
            "available": True,
            "features": features,
            "counts_by_kind": by_kind,
            "total": len(raw_features),
            "omitted_by_budget": omitted,
            "freshness_score": _freshness_score(features, ("updated_at",)),
            "provenance": [
                _source_provenance(
                    "drawing_features",
                    "available",
                    table="drawing_features",
                    total=len(raw_features),
                )
            ],
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
        raw_alerts = [_redact_context(_normalise_row_dict(r["payload"])) for r in rows]
        alerts, omitted = _budget_list(raw_alerts, max_items=_CONTEXT_MAX_ITEMS["alerts"])
        return {
            "available": True,
            "items": alerts,
            "total": len(raw_alerts),
            "omitted_by_budget": omitted,
            "freshness_score": _freshness_score(
                alerts, ("created_at", "updated_at", "occurred_at")
            ),
            "provenance": [
                _source_provenance("alerts", "available", table="alerts", total=len(raw_alerts))
            ],
        }, None
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
        raw_recommendations = [_redact_context(_normalise_row_dict(r["payload"])) for r in rows]
        recommendations, omitted = _budget_list(
            raw_recommendations, max_items=_CONTEXT_MAX_ITEMS["recommendations"]
        )
        return {
            "available": True,
            "items": recommendations,
            "total": len(raw_recommendations),
            "omitted_by_budget": omitted,
            "freshness_score": _freshness_score(
                recommendations, ("created_at", "updated_at", "issued_at")
            ),
            "provenance": [
                _source_provenance(
                    "recommendations",
                    "available",
                    table="recommendations",
                    total=len(raw_recommendations),
                )
            ],
        }, None
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "items": [], "total": 0}, f"تعذّر جلب التوصيات: {exc}"


def _ndvi_grid_from_raster_payload(
    payload: Any,
) -> tuple[list[list[float]] | None, dict[str, Any] | None]:
    """Pure extraction of a *real* NDVI grid + quality from a raster indicator-grid
    response (v62.3-C). Returns ``(None, None)`` unless the payload carries a real
    (non-synthetic) 2D grid, so simulation fallbacks never masquerade as evidence.

    Never fabricates: only quality keys actually present in the payload are copied;
    absent metrics are omitted. The v62.3-B quality fields
    (``valid_pixel_ratio``/``coverage_ratio``/``cloud_cover``) are read defensively
    since that slice lands in parallel and may not yet be populated.
    """
    if not isinstance(payload, dict):
        return None, None
    if payload.get("real_data") is not True:
        return None, None  # simulation / unknown ⇒ degrade to no grid (today's behavior)
    grid = payload.get("grid")
    if not (isinstance(grid, list) and grid and all(isinstance(r, list) for r in grid)):
        return None, None
    quality: dict[str, Any] = {}
    for key in (
        "cloud_cover",
        "cloud_pct",
        "valid_pixel_ratio",
        "coverage_ratio",
        "scene_id",
        "source_resolution_m",
        "asset_id",
    ):
        val = payload.get(key)
        if val is not None:
            quality[key] = val
    # acquisition_date: prefer an explicit field, else the grid's resolved date.
    acq = payload.get("acquisition_date") or payload.get("date")
    if acq is not None:
        quality["acquisition_date"] = acq
    return grid, (quality or None)


async def _optional_ndvi_grid(
    client: httpx.AsyncClient, raster_url: str, field_id: str, headers: dict[str, str]
) -> tuple[list[list[float]] | None, dict[str, Any] | None, str | None]:
    """Fetch the latest real NDVI grid + quality for the field (v62.3-C).

    Reuses the caller's tenant-scoped httpx client/base-URL/headers. Fail-safe: any
    raster error/timeout, or a synthetic/missing grid, degrades to ``(None, None)``
    so the pack is still built exactly as before (no grid attached).
    """
    try:
        resp = await client.get(
            f"{raster_url}/v1/fields/{field_id}/indicator-grid",
            params={"index": "ndvi", "date": "latest"},
            headers=headers,
        )
        resp.raise_for_status()
        grid, quality = _ndvi_grid_from_raster_payload(resp.json())
        return grid, quality, None
    except Exception as exc:  # noqa: BLE001 — raster outage never breaks the pack
        return None, None, f"ndvi_grid: {exc}"


async def _optional_imagery_timeline(
    field_id: str, tenant_id: str, days: int
) -> tuple[dict[str, Any], str | None]:
    raster_url = os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8001").rstrip("/")
    headers = {"X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", ""), "X-Tenant-Id": tenant_id}
    since = date.today() - timedelta(days=days)
    indicators = ["truecolor", "ndvi", "ndmi", "ndre", "msavi"]
    per_indicator: dict[str, Any] = {}
    warnings: list[str] = []
    ndvi_grid: list[list[float]] | None = None
    ndvi_grid_quality: dict[str, Any] | None = None
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
        # v62.3-C — also carry the latest *real* NDVI grid + quality so the AI pack can
        # fire the k-means productivity-zoning path and feed the VRA raster-quality gate.
        # Reuses the same tenant-scoped client; a raster outage degrades to no grid.
        ndvi_grid, ndvi_grid_quality, grid_warn = await _optional_ndvi_grid(
            client, raster_url, field_id, headers
        )
        if grid_warn:
            warnings.append(grid_warn)
    total_dates = sum(int(v.get("total", 0)) for v in per_indicator.values())
    result: dict[str, Any] = {
        "available": total_dates > 0,
        "range_days": days,
        "since": since.isoformat(),
        "until": date.today().isoformat(),
        "per_indicator": per_indicator,
        "total_dates": total_dates,
        "note_ar": "يعرض فقط المشاهد الموجودة/المجهزة؛ استخدم imagery/backfill custom months=24 لتجهيز سنتين.",
        "freshness_score": _freshness_score(
            [
                item
                for block in per_indicator.values()
                for item in (block.get("dates") or [])
                if isinstance(item, dict)
            ],
            ("date", "acquisition_date", "acquisition_datetime"),
        ),
        "provenance": [
            _source_provenance(
                "imagery_timeline",
                "available" if total_dates else "empty",
                service="raster-service",
                total=total_dates,
            )
        ],
    }
    # Additive: only attach when a real grid/quality is present (never fabricate).
    if ndvi_grid is not None:
        result["ndvi_grid"] = ndvi_grid
    if ndvi_grid_quality:
        result["ndvi_grid_quality"] = ndvi_grid_quality
    return result, ("؛ ".join(warnings) if warnings else None)


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
            "freshness_score": _freshness_score([{"date": summary.get("last_date")}], ("date",)),
            "provenance": [
                _source_provenance(
                    "weather_history", "available", service="open-meteo-archive", total=len(records)
                )
            ],
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
            operations, warn = await _optional_events(conn, field_id, str(user.tenant_id), 300)
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

    evidence_provenance: list[dict[str, Any]] = []
    for block in (imagery, weather, operations, drawings, alerts, recommendations):
        if isinstance(block, dict):
            evidence_provenance.extend(block.get("provenance") or [])

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
            "evidence_freshness_score": round(
                sum(
                    v
                    for v in (
                        imagery.get("freshness_score"),
                        weather.get("freshness_score"),
                        operations.get("freshness_score"),
                        drawings.get("freshness_score"),
                        alerts.get("freshness_score"),
                        recommendations.get("freshness_score"),
                    )
                    if isinstance(v, (int, float))
                )
                / max(
                    1,
                    len(
                        [
                            v
                            for v in (
                                imagery.get("freshness_score"),
                                weather.get("freshness_score"),
                                operations.get("freshness_score"),
                                drawings.get("freshness_score"),
                                alerts.get("freshness_score"),
                                recommendations.get("freshness_score"),
                            )
                            if isinstance(v, (int, float))
                        ]
                    ),
                ),
                3,
            ),
            "evidence_provenance": evidence_provenance,
        },
    }
    payload, context_budget, budget_warnings = _apply_final_context_budget(payload)
    payload["readiness"]["context_budget"] = context_budget
    payload["readiness"]["warnings"].extend(budget_warnings)
    payload["readiness"]["complete"] = not payload["readiness"]["warnings"]
    payload["ai_context_summary_ar"] = _summary_ar(payload)
    return FieldAiContextPack(**payload)
