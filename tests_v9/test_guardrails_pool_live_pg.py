"""Live-PG proof of the guardrails approval pool owner (#1267), measured in backends.

The unit tests in ``test_guardrails_contract.py`` prove the lock and the shutdown
order with a fake pool. This file measures the same contract against a real
asyncpg pool: every pool this module creates tags its connections with a unique
``application_name``, and ``pg_stat_activity`` counts the backends.

  * six concurrent cold ``_get_pool()`` calls open exactly one pool (``min_size``
    backends), not six;
  * ``close_pool()`` leaves zero backends with that name;
  * a later ``_get_pool()`` opens a fresh pool, and closing it leaves zero again.

Runs with ``pytest -m integration``. With ``HIL_CERTIFICATION_REQUIRED=1`` a missing
database is a failure, not a skip (the CI Integration Tests job sets it).
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import uuid
from urllib.parse import urlencode, urlsplit, urlunsplit

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIL_PATH = os.path.join(ROOT, "services", "guardrails-engine", "human_in_loop.py")


def _load_hil():
    spec = importlib.util.spec_from_file_location("_hil_pool_live_pg", HIL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_hil_pool_live_pg"] = module
    spec.loader.exec_module(module)
    return module


def _database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL", "")
    if url:
        return url
    message = "live pool certificate requires explicit TEST_DATABASE_URL"
    if os.getenv("HIL_CERTIFICATION_REQUIRED") == "1":
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


def _with_application_name(url: str, name: str) -> str:
    parts = urlsplit(url)
    query = "&".join(q for q in (parts.query, urlencode({"application_name": name})) if q)
    return urlunsplit(parts._replace(query=query))


async def _backends(url: str, name: str) -> int:
    import asyncpg

    conn = await asyncpg.connect(url, statement_cache_size=0)
    try:
        return await conn.fetchval(
            "SELECT count(*) FROM pg_stat_activity WHERE application_name = $1", name
        )
    finally:
        await conn.close()


async def _wait_for(url: str, name: str, expected: int, timeout: float = 5.0) -> int:
    """Backends leave pg_stat_activity shortly after close; poll instead of sleeping blind."""
    deadline = asyncio.get_running_loop().time() + timeout
    count = await _backends(url, name)
    while count != expected and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.05)
        count = await _backends(url, name)
    return count


@pytest.mark.integration
def test_cold_concurrency_shutdown_and_restart_measured_in_backends():
    url = _database_url()
    hil = _load_hil()
    name = f"sahool-hil-pool-{uuid.uuid4().hex[:12]}"
    hil.DATABASE_URL = _with_application_name(url, name)
    hil._pool = None
    hil._pool_lock = asyncio.Lock()

    async def scenario():
        try:
            await asyncio.wait_for(_backends(url, name), timeout=10.0)
        except Exception as exc:  # noqa: BLE001 - the database is the precondition
            message = f"live pool database unavailable: {type(exc).__name__}"
            if os.getenv("HIL_CERTIFICATION_REQUIRED") == "1":
                pytest.fail(message, pytrace=False)
            pytest.skip(message)

        pools = await asyncio.gather(*(hil._get_pool() for _ in range(6)))
        first = pools[0]
        assert all(pool is first for pool in pools), "concurrent cold callers got different pools"
        assert await _wait_for(url, name, 1) == 1, "six cold callers opened more than one pool"

        await hil.close_pool()
        assert hil._pool is None
        assert await _wait_for(url, name, 0) == 0, "close_pool left backends open"

        again = await hil._get_pool()
        assert again is not first, "restart reused the closed pool"
        assert await _wait_for(url, name, 1) == 1
        await hil.close_pool()
        assert await _wait_for(url, name, 0) == 0

    asyncio.run(scenario())
