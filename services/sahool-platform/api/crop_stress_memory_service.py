"""Application service for rebuilding durable Crop Intelligence stress memory."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from core.crop_intelligence.stress_memory import build_stress_memory

from api.crop_stress_store import load_stress_events, persist_stress_snapshot


def _as_utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def rebuild_stress_memory_snapshot(
    conn: Any,
    *,
    tenant_id: UUID,
    field_id: str,
    season_id: str,
    as_of: datetime | str,
    half_life_days: float = 7.0,
    max_age_days: float = 45.0,
) -> dict[str, Any]:
    """Load raw events, rebuild the canonical reducer, and persist a snapshot."""
    as_of_dt = _as_utc(as_of)
    since = as_of_dt - timedelta(days=max_age_days)
    events = await load_stress_events(
        conn,
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        since=since,
        until=as_of_dt,
    )
    source_ids = [
        event["evidence_id"] for event in events if isinstance(event.get("evidence_id"), str)
    ]
    snapshot = build_stress_memory(
        events,
        as_of=as_of_dt,
        half_life_days=half_life_days,
        max_age_days=max_age_days,
        source_ids=source_ids,
    )
    persistence = await persist_stress_snapshot(
        conn,
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        snapshot=snapshot,
    )
    return {
        "status": "snapshot_ready",
        "field_id": field_id,
        "season_id": season_id,
        "event_count": len(events),
        "snapshot": snapshot,
        "persistence": persistence,
    }
