"""Durable persistence adapter for Crop Intelligence stress memory.

Raw stress observations are the source of truth. Snapshots are derived,
versioned read models and can always be recomputed from raw events.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

_ALLOWED_TYPES = {"water", "heat", "cold", "nutrient", "disease"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("observed_at/as_of must be an ISO-8601 datetime")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def validate_stress_event(event: dict[str, Any]) -> dict[str, Any]:
    kind = str(event.get("type") or "").lower()
    if kind not in _ALLOWED_TYPES:
        raise ValueError("unsupported stress type")
    severity = event.get("severity")
    if isinstance(severity, bool) or not isinstance(severity, (int, float)):
        raise ValueError("severity must be numeric")
    severity = float(severity)
    if not 0 <= severity <= 1:
        raise ValueError("severity must be within [0,1]")
    observed_at = _parse_time(event.get("observed_at"))
    source_service = str(event.get("source_service") or "").strip()
    if not source_service:
        raise ValueError("source_service is required")
    normalized = {
        "type": kind,
        "severity": severity,
        "observed_at": observed_at,
        "evidence_id": event.get("evidence_id"),
        "source_service": source_service,
        "source_product_id": event.get("source_product_id"),
        "source_version": event.get("source_version"),
        "payload": event.get("payload") or {},
    }
    normalized["dedup_key"] = str(event.get("dedup_key") or _digest(normalized))
    return normalized


async def append_stress_event(
    conn: Any,
    *,
    tenant_id: UUID,
    field_id: str,
    season_id: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    item = validate_stress_event(event)
    row = await conn.fetchrow(
        """
        INSERT INTO crop_stress_events
            (tenant_id, field_id, season_id, stress_type, severity, observed_at,
             evidence_id, source_service, source_product_id, source_version, payload, dedup_key)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12)
        ON CONFLICT (tenant_id, dedup_key) DO NOTHING
        RETURNING event_id
        """,
        tenant_id,
        field_id,
        season_id,
        item["type"],
        item["severity"],
        item["observed_at"],
        item["evidence_id"],
        item["source_service"],
        item["source_product_id"],
        item["source_version"],
        _json(item["payload"]),
        item["dedup_key"],
    )
    return {
        "persisted": row is not None,
        "deduplicated": row is None,
        "dedup_key": item["dedup_key"],
    }


async def load_stress_events(
    conn: Any,
    *,
    tenant_id: UUID,
    field_id: str,
    season_id: str,
    since: datetime,
    until: datetime,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT stress_type, severity, observed_at, evidence_id, source_service,
               source_product_id, source_version, payload
        FROM crop_stress_events
        WHERE tenant_id=$1 AND field_id=$2 AND season_id=$3
          AND observed_at >= $4 AND observed_at <= $5
        ORDER BY observed_at ASC, event_id ASC
        """,
        tenant_id,
        field_id,
        season_id,
        since,
        until,
    )
    return [
        {
            "type": row["stress_type"],
            "severity": float(row["severity"]),
            "observed_at": row["observed_at"].astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "evidence_id": row["evidence_id"],
            "source_service": row["source_service"],
            "source_product_id": row["source_product_id"],
            "source_version": row["source_version"],
            "payload": row["payload"],
        }
        for row in rows
    ]


async def persist_stress_snapshot(
    conn: Any,
    *,
    tenant_id: UUID,
    field_id: str,
    season_id: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    as_of = _parse_time(snapshot.get("as_of"))
    evidence_digest = _digest(snapshot.get("evidence_ids") or [])
    row = await conn.fetchrow(
        """
        INSERT INTO crop_stress_memory_snapshots
            (tenant_id, field_id, season_id, as_of, schema_version, product_version,
             status, overall_burden, recovery_state, observation_count, snapshot, evidence_digest)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12)
        ON CONFLICT (tenant_id, field_id, season_id, as_of, product_version, evidence_digest)
        DO NOTHING
        RETURNING snapshot_id
        """,
        tenant_id,
        field_id,
        season_id,
        as_of,
        str(snapshot.get("schema")),
        str(snapshot.get("product_version")),
        str(snapshot.get("status")),
        snapshot.get("overall_burden"),
        str(snapshot.get("recovery_state") or "unknown"),
        int(snapshot.get("observation_count") or 0),
        _json(snapshot),
        evidence_digest,
    )
    return {
        "persisted": row is not None,
        "deduplicated": row is None,
        "evidence_digest": evidence_digest,
    }
