"""Bounded shutdown of asyncpg pools (sahool-platform's ``api/main.py`` and other services).

Kept out of that file, whose size the P1 decomposition guard caps. Stdlib only. Each pool is
closed within a bound; on timeout or close failure it is terminated, and if shutdown is
cancelled partway the pools not yet closed are terminated too, so no backend stays open.
Background tasks that use a pool are cancelled and awaited first, so none races the close;
the other awaits of a shutdown (a task asked to stop, a redis client) get the same bound.
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


async def cancel_tasks_bounded(tasks: list[Any], label: str) -> None:
    """Cancel background tasks and wait (within the bound) until they stop, skipping None.

    Called before a pool is closed: a task still running would hold a connection that
    ``close()`` waits for, or acquire from a pool that is going away.
    """
    live = [task for task in tasks if task is not None]
    for task in live:
        task.cancel()
    if not live:
        return
    _, pending = await asyncio.wait(live, timeout=POOL_CLOSE_TIMEOUT_SECONDS)
    if pending:
        logging.warning("%s: %d background task(s) ignored cancel", label, len(pending))
    for task in live:
        if task.done() and not task.cancelled():
            task.exception()  # mark a task that failed on its own as retrieved


async def stop_task_bounded(task: Any, label: str) -> None:
    """Wait (within the bound) for a task already asked to stop; cancel it if it does not.

    A task that failed on its own is logged, not raised, so the pool close after it still runs.
    """
    if task is None:
        return
    _, pending = await asyncio.wait([task], timeout=POOL_CLOSE_TIMEOUT_SECONDS)
    if pending:
        logging.warning("%s ignored stop; cancelling", label)
        await cancel_tasks_bounded([task], label)
    elif not task.cancelled() and task.exception() is not None:
        logging.warning("%s failed (%s)", label, type(task.exception()).__name__)


async def close_client_bounded(client: Any, label: str) -> None:
    """Close a client with an async ``close()`` (e.g. redis) within the bound, skipping None."""
    if client is None:
        return
    try:
        await asyncio.wait_for(client.close(), timeout=POOL_CLOSE_TIMEOUT_SECONDS)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — timeout or close failure: shutdown goes on
        logging.warning("%s close failed (%s); dropping it", label, type(exc).__name__)
