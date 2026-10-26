"""Live-PG proof of the pool owners fixed by the create_pool audit, measured in backends.

``test_pool_single_owner_audit.py`` proves the locks and the shutdown order with a fake
pool. This file measures the same contract against real asyncpg pools: every pool tags
its connections with a unique ``application_name`` and ``pg_stat_activity`` counts them.

  * decision-service ``acquire_connection``: six concurrent cold callers open one pool
    (``min_size`` = 1 backend), ``close_pools()`` leaves zero, a restart opens a fresh one;
  * vegetation ``PostgresAnomalyStore``: the same for ``_get_pool()`` / ``close()``;
  * platform ``_close_db_pool``: both the app pool and the jobs pool leave zero backends.

Runs with ``pytest -m integration``. With ``HIL_CERTIFICATION_REQUIRED=1`` a missing
database is a failure, not a skip (as in ``test_guardrails_pool_live_pg.py``).
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
DECISION = os.path.join(ROOT, "services", "decision-service")
VEGETATION = os.path.join(ROOT, "services", "vegetation-analysis-service")
PLATFORM = os.path.join(ROOT, "services", "sahool-platform")


def _load(name: str, path: str, *, deps: dict[str, str] | None = None):
    saved = {dep: sys.modules.get(dep) for dep in deps or {}}
    try:
        for dep, dep_path in (deps or {}).items():
            spec = importlib.util.spec_from_file_location(dep, dep_path)
            sys.modules[dep] = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(sys.modules[dep])
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for dep, previous in saved.items():
            if previous is None:
                sys.modules.pop(dep, None)
            else:
                sys.modules[dep] = previous


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


async def _require_database(url: str) -> None:
    try:
        await asyncio.wait_for(_backends(url, "probe"), timeout=10.0)
    except Exception as exc:  # noqa: BLE001 - the database is the precondition
        message = f"live pool database unavailable: {type(exc).__name__}"
        if os.getenv("HIL_CERTIFICATION_REQUIRED") == "1":
            pytest.fail(message, pytrace=False)
        pytest.skip(message)


@pytest.mark.integration
def test_decision_pool_cold_concurrency_shutdown_and_restart_measured_in_backends(monkeypatch):
    url = _database_url()
    mod = _load("_decision_persistence_live_pg", os.path.join(DECISION, "persistence.py"))
    name = f"sahool-decision-pool-{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(mod, "database_url", lambda: _with_application_name(url, name))
    # max_size=1: one shared pool serialises the callers on one backend; six pools hold six.
    monkeypatch.setenv("DECISION_DB_POOL_MAX", "1")

    async def use_once():
        conn = await mod.acquire_connection()
        try:
            await conn.fetchval("SELECT 1")
            return id(conn._pool)
        finally:
            await conn.close()

    async def scenario():
        await _require_database(url)
        pools = set(await asyncio.gather(*(use_once() for _ in range(6))))
        assert await _wait_for(url, name, 1) == 1, "six cold callers opened more than one pool"
        assert len(pools) == 1, "concurrent cold callers got different pools"

        await mod.close_pools()
        assert mod._POOLS == {}
        assert await _wait_for(url, name, 0) == 0, "close_pools left backends open"

        conn = await mod.acquire_connection()
        await conn.close()
        assert await _wait_for(url, name, 1) == 1, "restart did not open a fresh pool"
        await mod.close_pools()
        assert await _wait_for(url, name, 0) == 0

    try:
        asyncio.run(scenario())
    finally:
        sys.modules.pop("_decision_persistence_live_pg", None)


@pytest.mark.integration
def test_anomaly_store_pool_cold_concurrency_shutdown_and_restart_measured_in_backends():
    url = _database_url()
    mod = _load(
        "_anomaly_store_pg_live_pg",
        os.path.join(VEGETATION, "anomaly_store_pg.py"),
        deps={"anomaly_store": os.path.join(VEGETATION, "anomaly_store.py")},
    )
    name = f"sahool-anomaly-pool-{uuid.uuid4().hex[:12]}"
    store = mod.PostgresAnomalyStore(_with_application_name(url, name))

    async def scenario():
        await _require_database(url)
        pools = await asyncio.gather(*(store._get_pool() for _ in range(6)))
        assert all(pool is pools[0] for pool in pools), (
            "concurrent cold callers got different pools"
        )
        assert await _wait_for(url, name, 1) == 1, "six cold callers opened more than one pool"

        await store.close()
        assert store._pool is None
        assert await _wait_for(url, name, 0) == 0, "close left backends open"

        again = await store._get_pool()
        assert again is not pools[0]
        assert await _wait_for(url, name, 1) == 1
        await store.close()
        assert await _wait_for(url, name, 0) == 0

    try:
        asyncio.run(scenario())
    finally:
        sys.modules.pop("_anomaly_store_pg_live_pg", None)


@pytest.mark.integration
def test_platform_shutdown_leaves_no_app_or_jobs_backends(monkeypatch):
    url = _database_url()
    pytest.importorskip("fastapi")
    app_name = f"sahool-platform-app-{uuid.uuid4().hex[:12]}"
    jobs_name = f"sahool-platform-jobs-{uuid.uuid4().hex[:12]}"
    monkeypatch.setenv("DATABASE_URL", _with_application_name(url, app_name))
    monkeypatch.setenv("JOBS_DATABASE_URL", _with_application_name(url, jobs_name))
    monkeypatch.setenv("DB_POOL_MIN", "1")
    monkeypatch.setenv("DB_POOL_MAX", "2")
    # This measures pool ownership, not the role guard: the disposable test role may be a
    # superuser, so take the documented development escape instead of refusing startup.
    monkeypatch.setenv("SAHOOL_ALLOW_RLS_BYPASS_ROLE", "1")
    monkeypatch.syspath_prepend(PLATFORM)
    import api.main as main

    monkeypatch.setattr(main, "_DB_POOL", None)
    monkeypatch.setattr(main, "_JOBS_POOL", None)

    async def scenario():
        await _require_database(url)
        await main._init_db_pool()
        assert main._DB_POOL is not None and main._JOBS_POOL is not None
        assert await _wait_for(url, app_name, 1) == 1
        assert await _wait_for(url, jobs_name, 1) == 1

        await main._close_db_pool()
        assert await _wait_for(url, app_name, 0) == 0, "app pool left backends open"
        assert await _wait_for(url, jobs_name, 0) == 0, "jobs pool left backends open"

    asyncio.run(scenario())
