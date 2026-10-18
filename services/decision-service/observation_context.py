"""Read-only authoritative delivery context for imagery scheduling."""

from __future__ import annotations

import persistence


async def read_context(tenant: str, execution_request_id: str) -> dict | None:
    conn = await persistence._connect()
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            row = await conn.fetchrow(
                """SELECT r.execution_request_id,r.receipt_id,r.received_at,
                          d.field_id,d.season_id
                   FROM decision_execution_requests r
                   JOIN decision_execution_delivery_attempts a
                     ON a.tenant_id=r.tenant_id AND a.execution_request_id=r.execution_request_id
                   JOIN decision_record d ON d.tenant_id=r.tenant_id AND d.decision_id=r.decision_id
                   WHERE r.tenant_id=$1::uuid AND r.execution_request_id=$2
                     AND r.status='accepted' AND r.receipt_status='accepted'
                     AND a.receipt_status='accepted' AND a.receipt_id=r.receipt_id
                     AND r.received_at IS NOT NULL""",
                tenant,
                execution_request_id,
            )
            if row is None:
                return None
            return {
                **dict(row),
                "tenant_id": tenant,
                "received_at": row["received_at"].isoformat(),
                "time_basis": "delivery_receipt_received_at",
                "physical_execution_verified": False,
            }
    finally:
        await conn.close()
