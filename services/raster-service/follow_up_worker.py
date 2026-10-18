"""One-at-a-time durable scheduler, independent of request lifetime.

Only idempotent downstream hand-offs run here. The existing backfill worker owns
pixels and persistence; Decision SoR continues to own outcome verification.
"""

from __future__ import annotations

import asyncio
import logging
import random

from follow_up_store import FollowUpStore

logger = logging.getLogger(__name__)


class RetryLater(Exception):
    def __init__(self, code: str, *, no_scene: bool = False):
        self.code = code
        self.no_scene = no_scene


class PermanentFailure(Exception):
    pass


async def run_once(store: FollowUpStore, tenant: str, process) -> bool:
    row = await store.claim(tenant)
    if row is None:
        return False
    try:
        # Less than the 180s lease. Do not renew a whole batch while spending it serially.
        async with asyncio.timeout(120):
            result = await process(row, store)
        await store.settle(row, status="dispatched", result=result)
    except PermanentFailure as exc:
        await store.settle(row, status="failed", reason=str(exc))
    except RetryLater as exc:
        delay = 21600 if exc.no_scene else retry_delay(row["attempts"])
        await store.settle(
            row,
            status="waiting_for_scene" if exc.no_scene else "retry_wait",
            reason=exc.code,
            delay_seconds=delay,
        )
    except TimeoutError:
        await store.settle(
            row,
            status="retry_wait",
            reason="upstream_timeout",
            delay_seconds=retry_delay(row["attempts"]),
        )
    # Unexpected failures/cancellation leave the durable lease for recovery. Never
    # serialize exceptions (which may contain tokens/URLs) into public job status.
    return True


def retry_delay(attempt: int) -> int:
    ceiling = min(3600, 60 * (2 ** min(max(attempt - 1, 0), 6)))
    return random.randint(max(1, ceiling // 2), ceiling)


async def serve(tenants: tuple[str, ...], store: FollowUpStore, process):
    while True:
        did_work = False
        for tenant in tenants:
            try:
                did_work = await run_once(store, tenant, process) or did_work
            except Exception as exc:  # noqa: BLE001 — retry loop; cancellation propagates
                logger.error("follow-up iteration failed: %s", type(exc).__name__)
        await asyncio.sleep(1 if did_work else 15)
