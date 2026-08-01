"""Durable SoilProfileSnapshot projection queue.

PostgreSQL is the queue of record. Claims use SKIP LOCKED and leases; retries are
bounded and terminal failures move to ``dead_letter`` without losing evidence.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import Any

import projection_observability as obs
import soil_store

logger = logging.getLogger("soil-service.projection-jobs")
MAX_ATTEMPTS = int(os.getenv("SOIL_PROJECTION_MAX_ATTEMPTS", "8"))
LEASE_SECONDS = int(os.getenv("SOIL_PROJECTION_LEASE_SECONDS", "120"))
POLL_SECONDS = float(os.getenv("SOIL_PROJECTION_POLL_SECONDS", "2"))


async def enqueue(conn, *, tenant_id: str, field_id: str, reason: str) -> None:
    """Coalesce active work per tenant/field; completed history remains immutable."""
    await conn.execute(
        """
        INSERT INTO soil_profile_projection_jobs(tenant_id, field_id, reason)
        VALUES ($1::uuid, $2, $3)
        ON CONFLICT (tenant_id, field_id)
          WHERE status IN ('pending','running','retry')
        DO UPDATE SET reason=EXCLUDED.reason, available_at=LEAST(
            soil_profile_projection_jobs.available_at, NOW()
        ), updated_at=NOW()
        """,
        tenant_id,
        field_id,
        reason,
    )


async def claim(pool, *, worker_id: str) -> dict[str, Any] | None:
    row = await pool.fetchrow(
        "SELECT * FROM sahool_claim_soil_projection_job($1,$2)",
        worker_id,
        LEASE_SECONDS,
    )
    return dict(row) if row else None


async def complete(pool, job_id: int) -> None:
    await pool.execute("SELECT sahool_finish_soil_projection_job($1,'completed',0,NULL)", job_id)


async def fail(pool, *, job_id: int, attempts: int, error: str) -> None:
    terminal = attempts >= MAX_ATTEMPTS
    delay = min(900, 2 ** min(attempts, 9))
    await pool.execute(
        "SELECT sahool_finish_soil_projection_job($1,$2,$3,$4)",
        job_id,
        "dead_letter" if terminal else "retry",
        delay,
        error[:4000],
    )


async def run_once(pool, *, worker_id: str) -> bool:
    job = await claim(pool, worker_id=worker_id)
    if not job:
        return False
    obs.JOBS_CLAIMED.inc()
    try:
        with obs.JOB_DURATION.time():
            await soil_store.rebuild_snapshot_locked(
                pool, tenant_id=job["tenant_id"], field_id=job["field_id"]
            )
        await complete(pool, int(job["job_id"]))
        obs.JOBS_COMPLETED.inc()
    except Exception as exc:  # durable retry boundary
        logger.exception("soil projection failed job_id=%s", job["job_id"])
        terminal = int(job["attempts"]) >= MAX_ATTEMPTS
        await fail(pool, job_id=int(job["job_id"]), attempts=int(job["attempts"]), error=repr(exc))
        obs.JOBS_FAILED.labels(terminal="true" if terminal else "false").inc()
    return True


async def worker_loop(pool, *, stop: asyncio.Event, worker_id: str) -> None:
    obs.WORKER_UP.set(1)
    try:
        while not stop.is_set():
            worked = await run_once(pool, worker_id=worker_id)
            if not worked:
                # EXPECTED-CONTROL-FLOW-EXCEPTION — نوم قابل للمقاطعة، لا ابتلاع خطأ.
                # `wait_for(stop.wait(), timeout)` يعود مبكراً إن رُفِع علم التوقّف،
                # ويرفع `TimeoutError` على المسار **العاديّ** حين تنقضي فترة الاستطلاع.
                # فالاستثناء يقع مرّة كلّ `POLL_SECONDS` **إلى الأبد**: تسجيله يُنتِج
                # ضجيجاً يتناسب مع زمن التشغيل — العيب نفسه في الاتّجاه المعاكس.
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
    finally:
        obs.WORKER_UP.set(0)
