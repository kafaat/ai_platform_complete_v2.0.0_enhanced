"""IRR-F01 reservation lifecycle recovery worker.

Expires elapsed ``reserved`` reservations through the governed v205 transition function.
The worker is tenant-aware, uses short transactions, and is safe to run concurrently because
``expire_due`` selects rows with ``FOR UPDATE SKIP LOCKED``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from uuid import UUID

from api.irrigation_reservation_lifecycle import expire_due
from api.worker_heartbeat import HeartbeatState

logger = logging.getLogger("sahool.irrigation.reservation_lifecycle")

# WORKERS-INHERIT-AN-HTTP-HEALTHCHECK-THEY-CANNOT-ANSWER-01: هذا العامل يعمل من صورة
# المنصّة التي تحمل `HEALTHCHECK curl http://localhost:8000/healthz` في الـDockerfile، ولا
# يخدم HTTP — فكان يُقرأ **unhealthy دائماً** بلا أن يفعل شيئاً خطأ. النبضةُ هنا هي ما
# يقرأه `python -m api.worker_heartbeat check --worker <WORKER_NAME>` من compose (نفسُ نمط
# عمّال `phase_runtime_workers`)، فتصير الصحّةُ قياساً لدورة الكنس لا لمنفذٍ لا يُصغي أحد.
WORKER_NAME = "irrigation-reservation-lifecycle"


def poll_seconds() -> float:
    raw = os.getenv("IRRIGATION_RESERVATION_LIFECYCLE_POLL_SECONDS", "15")
    try:
        value = float(raw)
    except ValueError:
        value = 15.0
    return max(1.0, value)


async def expire_all_tenants(pool) -> int:
    """Run one bounded sweep; requires the dedicated cross-tenant worker DB role."""
    total = 0
    async with pool.acquire() as conn:
        tenant_rows = await conn.fetch(
            """SELECT DISTINCT tenant_id
                 FROM irrigation_resource_reservations
                WHERE state='reserved' AND upper(active_interval) <= NOW()
                ORDER BY tenant_id"""
        )
    for row in tenant_rows:
        tenant_id = UUID(str(row["tenant_id"]))
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true)", str(tenant_id)
                )
                total += await expire_due(conn, tenant_id=tenant_id)
    return total


async def sweep_once(pool, heartbeat: HeartbeatState) -> int:
    """One bounded sweep that always leaves a heartbeat behind it.

    A sweep that raises marks the heartbeat ``failed`` (the probe then reports the worker
    unhealthy with the error text) but never kills the loop — the next poll may succeed.
    Returns the number of expired reservations (0 on failure).
    """
    try:
        expired = await expire_all_tenants(pool)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — preserve worker liveness, surface full evidence
        logger.exception("reservation lifecycle sweep failed")
        heartbeat.mark_error(f"{type(exc).__name__}: {exc}")
        heartbeat.write()
        return 0
    if expired:
        logger.info("expired %s elapsed irrigation reservations", expired)
    heartbeat.mark_poll(expired)
    heartbeat.write()
    return expired


async def run() -> None:
    import asyncpg

    database_url = (os.getenv("JOBS_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("JOBS_DATABASE_URL or DATABASE_URL is required")
    heartbeat = HeartbeatState(WORKER_NAME)
    heartbeat.write()  # `starting` — the probe sees a fresh file before the first sweep
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3, command_timeout=30)
    delay = poll_seconds()
    logger.info("reservation lifecycle worker started; poll_seconds=%s", delay)
    try:
        while True:
            await sweep_once(pool, heartbeat)
            await asyncio.sleep(delay)
    finally:
        await pool.close()


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
