"""RS-6 durable multi-replica anomaly store (PostgreSQL + FORCE RLS).

Async asyncpg backend, opt-in via VEGETATION_ANOMALY_STORE=postgres. It mirrors
the SQLite store's semantics (optimistic-concurrency state machine) but is safe
for horizontal scale: tenant isolation is enforced by the DB (RLS policy from
migration v191), and app.current_tenant is set transaction-locally so pooled
connections never leak a tenant across requests.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import asyncpg
from anomaly_store import AnomalyNotFound, InvalidTransition, validate_transition

logger = logging.getLogger(__name__)
_POOL_CLOSE_TIMEOUT_SECONDS = 5.0


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is required for the postgres anomaly store")
    return url


class PostgresAnomalyStore:
    """Durable anomaly store; every method is tenant-scoped and RLS-bound."""

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn or _database_url()
        self._pool: asyncpg.Pool | None = None
        # One owner for the pool: concurrent cold callers share one creation.
        self._pool_lock = asyncio.Lock()

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            async with self._pool_lock:
                if self._pool is None:
                    self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=8)
        return self._pool

    async def close(self) -> None:
        """Close the pool at shutdown within a bound; a restart then creates a fresh one."""
        async with self._pool_lock:  # wait out an in-flight creation so it is closed, not leaked
            pool, self._pool = self._pool, None
        self._pool_lock = asyncio.Lock()
        if pool is None:
            return
        try:
            await asyncio.wait_for(pool.close(), timeout=_POOL_CLOSE_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            pool.terminate()
            raise
        except Exception as exc:  # timeout or close failure: never leave backends open
            logger.warning("Anomaly pool close failed (%s); terminating", type(exc).__name__)
            pool.terminate()

    async def _tenant_conn(self, conn: asyncpg.Connection, tenant_id: str) -> None:
        # Transaction-local so a pooled connection cannot carry a tenant across ops.
        await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant_id))

    @staticmethod
    def _row(row: asyncpg.Record) -> dict[str, Any]:
        payload = row["payload_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return {
            "anomaly_ref": row["anomaly_ref"],
            "tenant_id": str(row["tenant_id"]),
            "field_id": row["field_id"],
            "season_id": row["season_id"],
            "status": row["status"],
            "aggregate_version": int(row["version"]),
            "task_ref": row["task_ref"],
            "payload": payload,
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }

    async def upsert_detected(self, payload: dict[str, Any]) -> dict[str, Any]:
        ref = str(payload["anomaly_ref"])
        tenant = str(payload["tenant_id"])
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            await self._tenant_conn(conn, tenant)
            await conn.execute(
                """INSERT INTO signal_anomalies
                       (anomaly_ref, tenant_id, field_id, season_id, status, version,
                        payload_json)
                   VALUES ($1, $2::uuid, $3, $4, 'detected', 1, $5::jsonb)
                   ON CONFLICT (anomaly_ref) DO NOTHING""",
                ref,
                tenant,
                str(payload["field_id"]),
                str(payload["season_id"]),
                json.dumps(payload, sort_keys=True, default=str),
            )
            row = await conn.fetchrow("SELECT * FROM signal_anomalies WHERE anomaly_ref = $1", ref)
        return self._row(row)

    async def get(self, anomaly_ref: str, *, tenant_id: str) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            await self._tenant_conn(conn, tenant_id)
            row = await conn.fetchrow(
                "SELECT * FROM signal_anomalies WHERE anomaly_ref = $1", anomaly_ref
            )
        if not row:
            raise AnomalyNotFound(anomaly_ref)
        return self._row(row)

    async def list(self, tenant_id: str, field_id: str, season_id: str) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            await self._tenant_conn(conn, tenant_id)
            rows = await conn.fetch(
                """SELECT * FROM signal_anomalies
                   WHERE field_id = $1 AND season_id = $2
                   ORDER BY created_at DESC""",
                field_id,
                season_id,
            )
        return [self._row(r) for r in rows]

    async def transition(
        self,
        anomaly_ref: str,
        new_status: str,
        *,
        expected_version: int,
        patch: dict[str, Any] | None = None,
        task_ref: str | None = None,
        tenant_id: str,
    ) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            await self._tenant_conn(conn, tenant_id)
            row = await conn.fetchrow(
                "SELECT * FROM signal_anomalies WHERE anomaly_ref = $1 FOR UPDATE",
                anomaly_ref,
            )
            if not row:
                raise AnomalyNotFound(anomaly_ref)
            current = str(row["status"])
            if int(row["version"]) != expected_version:
                raise InvalidTransition("aggregate_version_conflict")
            payload = row["payload_json"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            validate_transition(current, new_status, payload, patch)
            payload.update(patch or {})
            payload["status"] = new_status
            payload["updated_at"] = datetime.now(UTC).isoformat()
            version = expected_version + 1
            updated_status = await conn.execute(
                """UPDATE signal_anomalies
                       SET status = $1, version = $2,
                           task_ref = COALESCE($3, task_ref),
                           payload_json = $4::jsonb, updated_at = now()
                   WHERE anomaly_ref = $5 AND version = $6""",
                new_status,
                version,
                task_ref,
                json.dumps(payload, sort_keys=True, default=str),
                anomaly_ref,
                expected_version,
            )
            if updated_status != "UPDATE 1":
                raise InvalidTransition("aggregate_version_conflict")
            row = await conn.fetchrow(
                "SELECT * FROM signal_anomalies WHERE anomaly_ref = $1", anomaly_ref
            )
        return self._row(row)
