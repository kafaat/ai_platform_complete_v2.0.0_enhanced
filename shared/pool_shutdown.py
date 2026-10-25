"""Bounded shutdown of asyncpg pools (used by sahool-platform's ``api/main.py``).

Kept out of that file, whose size the P1 decomposition guard caps. Stdlib only. Each pool is
closed within a bound; on timeout or close failure it is terminated, and if shutdown is
cancelled partway the pools not yet closed are terminated too, so no backend stays open.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

POOL_CLOSE_TIMEOUT_SECONDS = 5.0


async def close_pool_bounded(pool: Any, label: str) -> None:
    """Close one pool within a bound; on timeout, error or cancel terminate it instead."""
    try:
        await asyncio.wait_for(pool.close(), timeout=POOL_CLOSE_TIMEOUT_SECONDS)
    except asyncio.CancelledError:
        pool.terminate()
        raise
    except Exception as exc:  # noqa: BLE001 — timeout or close failure: never leave backends open
        logging.warning("%s pool close failed (%s); terminating", label, type(exc).__name__)
        pool.terminate()


async def close_pools_bounded(pools: list[tuple[Any, str]]) -> None:
    """Close each (pool, label) in order, skipping None; on cancel drop the rest too."""
    live = [(pool, label) for pool, label in pools if pool is not None]
    for index, (pool, label) in enumerate(live):
        try:
            await close_pool_bounded(pool, label)
        except asyncio.CancelledError:
            for rest, _ in live[index + 1 :]:  # cancelled mid-shutdown
                rest.terminate()
            raise
