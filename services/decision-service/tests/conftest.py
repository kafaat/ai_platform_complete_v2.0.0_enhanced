from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


@pytest.fixture(autouse=True)
async def _close_decision_service_pools():
    """Close the per-event-loop asyncpg pool after each test.

    ``persistence.acquire_connection`` caches an ``asyncpg`` pool keyed by event-loop
    id (``persistence._POOLS``). Under ``asyncio_mode = auto`` pytest-asyncio gives each
    async test its own loop, so the cache accumulates one never-closed pool per test —
    each holding a live server connection — and the suite exhausts Postgres
    ("FATAL: sorry, too many clients already"). Closing the current loop's pool on
    teardown (before the loop is torn down) releases those connections deterministically.
    """
    yield
    try:
        import asyncio

        import persistence

        pools = getattr(persistence, "_POOLS", None)
        if not pools:
            return
        pool = pools.pop(id(asyncio.get_event_loop()), None)
        if pool is not None:
            await pool.close()
    except Exception:
        pass


# Condition-1 determinism: the activation gate reads its build identity from DEPLOY_BUILD_SHA
# and fails closed if it is absent or not valid hex. Tests that don't exercise that failure
# path need a stable, valid 64-hex build identity; pin one deterministically here (a fixed
# value, never Date/random) so the whole suite runs against one known build fingerprint.
# Tests that assert the fail-closed behavior monkeypatch/delenv it locally.
os.environ.setdefault("DEPLOY_BUILD_SHA", "d" * 40)
os.environ.setdefault("ACTIVATION_EVIDENCE_SIGNING_KEY", "evidence-key")
