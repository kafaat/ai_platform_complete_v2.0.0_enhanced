"""Tenant-scoped durable timers; short transactions, expiring leases, fenced writes.

Schema belongs to v236. No startup DDL, Redis/memory fallback, service bearer storage,
or claim that a durable raster hand-off is an observed/verified agronomic outcome.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID, uuid4

from shared.contracts.imagery_followup import canonical_json

ACTIVE = ("pending", "claimed", "waiting_for_scene", "retry_wait")
LEASE_SECONDS = 180
MAX_ATTEMPTS = 128


class RequestConflict(ValueError):
    pass


def decode_row(row):
    if row is None:
        return None
    result = dict(row)
    for name in ("request_payload", "result_payload"):
        if isinstance(result.get(name), str):
            result[name] = json.loads(result[name])
    return result


async def connect():
    import asyncpg

    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        raise RuntimeError("follow_up_database_unconfigured")
    return await asyncpg.connect(dsn, timeout=5, command_timeout=10, statement_cache_size=0)


class FollowUpStore:
    def __init__(self, connection_factory=connect):
        self.connect = connection_factory

    @asynccontextmanager
    async def transaction(self, tenant: str):
        tenant = str(UUID(tenant))
        conn = await self.connect()
        try:
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
                yield conn
        finally:
            await conn.close()

    async def get(self, tenant: str, request_id: str):
        async with self.transaction(tenant) as conn:
            return decode_row(
                await conn.fetchrow(
                    "SELECT * FROM raster_follow_up_requests WHERE tenant_id=$1::uuid AND request_id=$2",
                    tenant,
                    request_id,
                )
            )

    async def enqueue(
        self,
        *,
        tenant: str,
        request_id: str,
        field_id: str,
        request_hash: str,
        payload: dict,
        due_at: datetime,
        expires_at: datetime,
    ):
        async with self.transaction(tenant) as conn:
            # DO NOTHING + a fresh READ COMMITTED statement sees the winning concurrent insert.
            await conn.execute(
                """INSERT INTO raster_follow_up_requests
                (tenant_id,request_id,field_id,request_hash,request_payload,due_at,expires_at,next_attempt_at)
                VALUES ($1::uuid,$2,$3,$4,$5::jsonb,$6,$7,$6)
                ON CONFLICT (tenant_id,request_id) DO NOTHING""",
                tenant,
                request_id,
                field_id,
                request_hash,
                canonical_json(payload),
                due_at,
                expires_at,
            )
            row = await conn.fetchrow(
                "SELECT * FROM raster_follow_up_requests WHERE tenant_id=$1::uuid AND request_id=$2",
                tenant,
                request_id,
            )
            if row["request_hash"] != request_hash:
                raise RequestConflict("follow_up_request_payload_mismatch")
            return decode_row(row)

    async def claim(self, tenant: str):
        token = uuid4()
        async with self.transaction(tenant) as conn:
            # Expiry and retry exhaustion are terminal; never leave overdue pending rows forever.
            await conn.execute(
                """UPDATE raster_follow_up_requests SET
                status=CASE WHEN expires_at<=now() THEN 'expired' ELSE 'failed' END,
                reason_code=CASE WHEN expires_at<=now() THEN 'observation_window_expired'
                                 ELSE 'attempt_budget_exhausted' END,
                lease_token=NULL,lease_until=NULL,updated_at=now()
                WHERE tenant_id=$1::uuid AND status=ANY($2::text[])
                  AND (status<>'claimed' OR lease_until<=now())
                  AND (expires_at<=now() OR attempts >= $3)""",
                tenant,
                list(ACTIVE),
                MAX_ATTEMPTS,
            )
            return decode_row(
                await conn.fetchrow(
                    """WITH candidate AS (
                  SELECT request_id FROM raster_follow_up_requests
                  WHERE tenant_id=$1::uuid AND status=ANY($2::text[])
                    AND due_at<=now() AND next_attempt_at<=now() AND expires_at>now()
                    AND (status<>'claimed' OR lease_until<=now()) AND attempts<$3
                  ORDER BY next_attempt_at,request_id FOR UPDATE SKIP LOCKED LIMIT 1
                ) UPDATE raster_follow_up_requests r SET status='claimed',lease_token=$4,
                  lease_until=LEAST(r.expires_at,now()+make_interval(secs=>$5)),
                  attempts=r.attempts+1,updated_at=now()
                FROM candidate c WHERE r.tenant_id=$1::uuid AND r.request_id=c.request_id
                RETURNING r.*""",
                    tenant,
                    list(ACTIVE),
                    MAX_ATTEMPTS,
                    token,
                    LEASE_SECONDS,
                )
            )

    async def owns(self, row: dict) -> bool:
        async with self.transaction(str(row["tenant_id"])) as conn:
            return bool(
                await conn.fetchval(
                    """SELECT EXISTS(SELECT 1 FROM raster_follow_up_requests
                WHERE tenant_id=$1::uuid AND request_id=$2 AND status='claimed'
                  AND lease_token=$3 AND lease_until>now() AND expires_at>now())""",
                    row["tenant_id"],
                    row["request_id"],
                    row["lease_token"],
                )
            )

    async def settle(
        self,
        row: dict,
        *,
        status: str,
        result: dict | None = None,
        reason: str | None = None,
        delay_seconds: int = 0,
    ) -> bool:
        if status not in {"dispatched", "failed", "waiting_for_scene", "retry_wait"}:
            raise ValueError("invalid follow-up transition")
        if status == "dispatched" and not (result and result.get("jobs")):
            raise ValueError("dispatched requires durable job references")
        if not 0 <= delay_seconds <= 86400:
            raise ValueError("invalid retry delay")
        async with self.transaction(str(row["tenant_id"])) as conn:
            outcome = await conn.execute(
                """UPDATE raster_follow_up_requests SET status=$4,result_payload=COALESCE($5::jsonb,result_payload),
                reason_code=$6,next_attempt_at=now()+make_interval(secs=>$7),
                lease_token=NULL,lease_until=NULL,updated_at=now()
                WHERE tenant_id=$1::uuid AND request_id=$2 AND status='claimed'
                  AND lease_token=$3 AND lease_until>now() AND expires_at>now()""",
                row["tenant_id"],
                row["request_id"],
                row["lease_token"],
                status,
                canonical_json(result) if result is not None else None,
                reason,
                delay_seconds,
            )
            return outcome == "UPDATE 1"

    async def save_progress(self, row: dict, result: dict) -> bool:
        async with self.transaction(str(row["tenant_id"])) as conn:
            return (
                await conn.execute(
                    """UPDATE raster_follow_up_requests SET result_payload=$4::jsonb,updated_at=now()
                WHERE tenant_id=$1::uuid AND request_id=$2 AND status='claimed'
                  AND lease_token=$3 AND lease_until>now() AND expires_at>now()""",
                    row["tenant_id"],
                    row["request_id"],
                    row["lease_token"],
                    canonical_json(result),
                )
                == "UPDATE 1"
            )

    async def cancel(self, tenant: str, request_id: str) -> bool:
        # Cancellation is possible only before a worker owns the hand-off. It cannot
        # recall already-created downstream jobs and must never claim otherwise.
        async with self.transaction(tenant) as conn:
            return (
                await conn.execute(
                    """UPDATE raster_follow_up_requests SET status='cancelled',updated_at=now()
                WHERE tenant_id=$1::uuid AND request_id=$2
                  AND status IN ('pending','waiting_for_scene','retry_wait')""",
                    tenant,
                    request_id,
                )
                == "UPDATE 1"
            )
