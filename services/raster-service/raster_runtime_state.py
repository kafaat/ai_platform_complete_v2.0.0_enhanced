"""Shared in-process runtime state for raster-service.

This module intentionally centralizes the remaining mutable registries while main.py
continues to re-export them as compatibility aliases for staged router migration.
"""

from __future__ import annotations

import os

from job_store import JobStore


def make_job_store(redis_url: str | None = None) -> JobStore:
    """Create the job store with the same Redis→memory fallback behavior as main.py."""
    return JobStore(redis_url=redis_url if redis_url is not None else os.getenv("REDIS_URL"))


JOBS = make_job_store()
LAYERS: dict[str, dict] = {}
FIELD_LAYERS: dict[str, list[str]] = {}
