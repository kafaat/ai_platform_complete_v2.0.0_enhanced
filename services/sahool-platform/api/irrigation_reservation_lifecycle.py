"""Legal reservation lifecycle and recovery operations backed by v197 transition function."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

TRANSITION_SQL = "SELECT * FROM transition_irrigation_reservation($1,$2,$3,$4,$5,$6)"
EXPIRED_SQL = """SELECT reservation_id FROM irrigation_resource_reservations
WHERE tenant_id=$1 AND state='reserved' AND upper(active_interval) <= $2 FOR UPDATE SKIP LOCKED"""


async def transition(
    conn: Any,
    *,
    tenant_id: UUID,
    reservation_id: UUID,
    target_state: str,
    reason: str | None = None,
    causation_id: UUID | None = None,
    correlation_id: UUID | None = None,
) -> Any:
    return await conn.fetchrow(
        TRANSITION_SQL,
        tenant_id,
        reservation_id,
        target_state,
        reason,
        causation_id,
        correlation_id,
    )


async def expire_due(conn: Any, *, tenant_id: UUID, now: datetime | None = None) -> int:
    instant = now or datetime.now(UTC)
    rows = await conn.fetch(EXPIRED_SQL, tenant_id, instant)
    for row in rows:
        await transition(
            conn,
            tenant_id=tenant_id,
            reservation_id=row["reservation_id"],
            target_state="expired",
            reason="interval_elapsed",
        )
    return len(rows)
