"""Operational metrics and health policy for the durable soil projection queue."""

from __future__ import annotations

import os
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

JOBS_CLAIMED = Counter("soil_projection_jobs_claimed_total", "Projection jobs claimed")
JOBS_COMPLETED = Counter("soil_projection_jobs_completed_total", "Projection jobs completed")
JOBS_FAILED = Counter("soil_projection_jobs_failed_total", "Projection jobs failed", ["terminal"])
JOB_DURATION = Histogram("soil_projection_job_duration_seconds", "Projection job processing time")
QUEUE_PENDING = Gauge("soil_projection_queue_pending", "Pending projection jobs")
QUEUE_RUNNING = Gauge("soil_projection_queue_running", "Running projection jobs")
QUEUE_RETRY = Gauge("soil_projection_queue_retry", "Retry projection jobs")
QUEUE_DEAD = Gauge("soil_projection_queue_dead_letter", "Dead-letter projection jobs")
QUEUE_EXPIRED = Gauge("soil_projection_queue_expired_leases", "Expired running leases")
QUEUE_OLDEST = Gauge("soil_projection_queue_oldest_ready_age_seconds", "Age of oldest ready job")
WORKER_UP = Gauge(
    "soil_projection_worker_up", "Whether the in-process projection worker is running"
)


def readiness_policy(stats: dict[str, Any]) -> tuple[bool, list[str]]:
    max_lag = float(os.getenv("SOIL_PROJECTION_READY_MAX_LAG_SECONDS", "300"))
    max_dead = int(os.getenv("SOIL_PROJECTION_READY_MAX_DEAD_LETTER", "0"))
    max_expired = int(os.getenv("SOIL_PROJECTION_READY_MAX_EXPIRED_LEASES", "0"))
    reasons: list[str] = []
    if float(stats.get("oldest_ready_age_seconds") or 0) > max_lag:
        reasons.append("projection_queue_lag")
    if int(stats.get("dead_letter") or 0) > max_dead:
        reasons.append("projection_dead_letter_present")
    if int(stats.get("expired_leases") or 0) > max_expired:
        reasons.append("projection_expired_leases")
    return not reasons, reasons


async def refresh_queue_metrics(pool) -> dict[str, Any]:
    row = await pool.fetchrow("SELECT * FROM sahool_soil_projection_queue_stats()")
    stats = dict(row) if row else {}
    QUEUE_PENDING.set(int(stats.get("pending") or 0))
    QUEUE_RUNNING.set(int(stats.get("running") or 0))
    QUEUE_RETRY.set(int(stats.get("retry") or 0))
    QUEUE_DEAD.set(int(stats.get("dead_letter") or 0))
    QUEUE_EXPIRED.set(int(stats.get("expired_leases") or 0))
    QUEUE_OLDEST.set(float(stats.get("oldest_ready_age_seconds") or 0))
    return stats
