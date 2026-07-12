"""Durable PostgreSQL lease store for raster batch jobs.

Redis remains a low-latency accelerator, but PostgreSQL is the authority for
cross-worker uniqueness and restart recovery. All operations are tenant-scoped
through app.current_tenant and fail honestly when the database is unavailable.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from typing import Any

DATABASE_URL = os.getenv("DATABASE_URL", "")
LEASE_SECONDS = max(30, int(os.getenv("RASTER_BATCH_LEASE_SECONDS", "300")))
WORKER_ID = os.getenv("RASTER_WORKER_ID", os.getenv("HOSTNAME", "raster-worker"))


@dataclass(frozen=True)
class DurableClaim:
    available: bool
    acquired: bool
    job_id: str
    status: str
    lease_owner: str | None = None
    lease_token: str | None = None
    recovered: bool = False


async def _connect():
    if not DATABASE_URL:
        return None
    try:
        import asyncpg

        return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception:
        return None


def _payload(req: Any) -> dict:
    if hasattr(req, "model_dump"):
        return req.model_dump(mode="json")
    return dict(req)


async def claim_or_recover(
    *,
    claim_key: str,
    job_id: str,
    tenant_id: str,
    field_id: str | None,
    req: Any,
    worker_id: str | None = None,
) -> DurableClaim:
    """Atomically create or lease a batch job.

    A completed/failed job is returned without re-execution. A pending job or a
    processing job with an expired lease can be acquired. A live lease remains
    owned by the existing worker and duplicate callers converge on its job_id.
    """
    conn = await _connect()
    if conn is None:
        return DurableClaim(False, False, job_id, "unavailable")
    owner = worker_id or WORKER_ID
    lease_token = uuid.uuid4().hex
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant_id))
            row = await conn.fetchrow(
                """
                INSERT INTO raster_batch_jobs (
                    claim_key, job_id, tenant_id, field_id, status,
                    lease_owner, lease_token, lease_expires_at, request_payload, attempt_count
                ) VALUES ($1,$2,$3,$4,'processing',$5,$8,now()+($6::text||' seconds')::interval,$7::jsonb,1)
                ON CONFLICT (claim_key) DO UPDATE SET
                    status = CASE
                        WHEN raster_batch_jobs.status='pending'
                          OR (raster_batch_jobs.status='processing' AND raster_batch_jobs.lease_expires_at < now())
                        THEN 'processing' ELSE raster_batch_jobs.status END,
                    lease_owner = CASE
                        WHEN raster_batch_jobs.status='pending'
                          OR (raster_batch_jobs.status='processing' AND raster_batch_jobs.lease_expires_at < now())
                        THEN EXCLUDED.lease_owner ELSE raster_batch_jobs.lease_owner END,
                    lease_token = CASE
                        WHEN raster_batch_jobs.status='pending'
                          OR (raster_batch_jobs.status='processing' AND raster_batch_jobs.lease_expires_at < now())
                        THEN EXCLUDED.lease_token ELSE raster_batch_jobs.lease_token END,
                    lease_expires_at = CASE
                        WHEN raster_batch_jobs.status='pending'
                          OR (raster_batch_jobs.status='processing' AND raster_batch_jobs.lease_expires_at < now())
                        THEN EXCLUDED.lease_expires_at ELSE raster_batch_jobs.lease_expires_at END,
                    attempt_count = CASE
                        WHEN raster_batch_jobs.status='pending'
                          OR (raster_batch_jobs.status='processing' AND raster_batch_jobs.lease_expires_at < now())
                        THEN raster_batch_jobs.attempt_count + 1 ELSE raster_batch_jobs.attempt_count END,
                    updated_at = now()
                RETURNING job_id, status, lease_owner, lease_token,
                          (lease_token=$8 AND status='processing') AS acquired,
                          (job_id<>$2 OR attempt_count>1) AS recovered
                """,
                claim_key,
                job_id,
                tenant_id,
                field_id,
                owner,
                LEASE_SECONDS,
                json.dumps(_payload(req), sort_keys=True),
                lease_token,
            )
        return DurableClaim(
            True,
            bool(row["acquired"]),
            str(row["job_id"]),
            str(row["status"]),
            row["lease_owner"],
            row["lease_token"],
            bool(row["recovered"]),
        )
    finally:
        await conn.close()


async def heartbeat(
    *, claim_key: str, tenant_id: str, lease_token: str, worker_id: str | None = None
) -> bool:
    conn = await _connect()
    if conn is None:
        return False
    owner = worker_id or WORKER_ID
    try:
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", str(tenant_id))
        result = await conn.execute(
            """UPDATE raster_batch_jobs
               SET lease_expires_at=now()+($3::text||' seconds')::interval, updated_at=now()
               WHERE claim_key=$1 AND lease_owner=$2 AND lease_token=$4 AND status='processing'""",
            claim_key,
            owner,
            LEASE_SECONDS,
            lease_token,
        )
        return result.endswith(" 1")
    finally:
        await conn.close()


async def finish(
    *,
    claim_key: str,
    tenant_id: str,
    lease_token: str,
    status: str,
    result_payload: dict | None = None,
    error_code: str | None = None,
    worker_id: str | None = None,
) -> bool:
    if status not in {"completed", "failed"}:
        raise ValueError("terminal status required")
    conn = await _connect()
    if conn is None:
        return False
    owner = worker_id or WORKER_ID
    try:
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", str(tenant_id))
        result = await conn.execute(
            """UPDATE raster_batch_jobs
               SET status=$3, result_payload=$4::jsonb, error_code=$5,
                   lease_owner=NULL, lease_expires_at=NULL,
                   completed_at=now(), updated_at=now()
               WHERE claim_key=$1 AND lease_owner=$2 AND lease_token=$6 AND status='processing'""",
            claim_key,
            owner,
            status,
            json.dumps(result_payload, sort_keys=True) if result_payload is not None else None,
            error_code,
            lease_token,
        )
        return result.endswith(" 1")
    finally:
        await conn.close()


def _run_sync(coro) -> bool:
    """Run a small DB coroutine from the synchronous background worker."""
    import asyncio
    import threading

    holder = {"value": False}
    try:
        holder["value"] = bool(asyncio.run(coro))
    except RuntimeError:

        def runner():
            holder["value"] = bool(asyncio.run(coro))

        t = threading.Thread(target=runner, daemon=True)
        t.start()
        t.join(timeout=30)
    return holder["value"]


def heartbeat_sync(
    *, claim_key: str, tenant_id: str, lease_token: str, worker_id: str | None = None
) -> bool:
    return _run_sync(
        heartbeat(
            claim_key=claim_key, tenant_id=tenant_id, lease_token=lease_token, worker_id=worker_id
        )
    )


def finish_sync(
    *,
    claim_key: str,
    tenant_id: str,
    lease_token: str,
    status: str,
    result_payload: dict | None = None,
    error_code: str | None = None,
    worker_id: str | None = None,
) -> bool:
    return _run_sync(
        finish(
            claim_key=claim_key,
            tenant_id=tenant_id,
            lease_token=lease_token,
            status=status,
            result_payload=result_payload,
            error_code=error_code,
            worker_id=worker_id,
        )
    )
