"""Production persistence policy for raster processing jobs.

This module centralizes the contract that a processed raster is not a published
agricultural asset until durable persistence succeeds. Development deployments
may retain best-effort processing, but those results are explicitly marked
``processed_unpublished`` and cannot enter downstream truth paths.
"""

from __future__ import annotations

import os
from enum import StrEnum


class PersistenceMode(StrEnum):
    REQUIRED = "required"
    BEST_EFFORT = "best_effort"


def persistence_mode() -> PersistenceMode:
    raw = os.getenv("RASTER_PERSISTENCE_MODE", "required").strip().lower()
    try:
        return PersistenceMode(raw)
    except ValueError as exc:
        raise RuntimeError("RASTER_PERSISTENCE_MODE must be 'required' or 'best_effort'") from exc


def terminal_status(*, persisted: bool) -> tuple[str, str | None]:
    """Return job status and optional error code after processing.

    ``completed`` is reserved for durably persisted assets. In best-effort mode,
    a successfully processed but non-persisted result is honest and queryable as
    ``processed_unpublished``; it must not be consumed as production truth.
    """
    if persisted:
        return "completed", None
    if persistence_mode() is PersistenceMode.REQUIRED:
        return "failed", "raster_asset_persistence_failed"
    return "processed_unpublished", "raster_asset_not_persisted"
