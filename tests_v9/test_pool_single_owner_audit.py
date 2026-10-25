"""Single pool owner for the lazy asyncpg pools found by the create_pool audit.

The #1267 pattern (``human_in_loop._get_pool``/``close_pool``) applied to the other sites
that had a real race or leak, proven with a fake pool:

  * decision-service ``persistence.acquire_connection``: concurrent cold callers on one
    loop each opened a pool (all but the last leaked), and nothing closed it on shutdown;
  * vegetation ``PostgresAnomalyStore._get_pool``: the same unlocked lazy creation, and
    the store had no close at all;
  * platform ``_close_db_pool``: closed the app pool but never the jobs pool.

Shutdown closes within a bound and terminates on timeout; lifespan wiring is exercised in
a subprocess so each service keeps its own deployment-local imports.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import textwrap

import pytest

pytestmark = pytest.mark.unit
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECISION = os.path.join(ROOT, "services", "decision-service")
VEGETATION = os.path.join(ROOT, "services", "vegetation-analysis-service")
PLATFORM = os.path.join(ROOT, "services", "sahool-platform")


class FakePool:
    def __init__(self, close_hangs=False):
        self.close_hangs = close_hangs
        self.closed = False
        self.terminated = False

    async def acquire(self):
        return object()

    async def release(self, conn):
        return None

    async def close(self):
        if self.close_hangs:
            await asyncio.Event().wait()
        self.closed = True

    def terminate(self):
        self.terminated = True


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


def _fake_create_pool(created, *, hang=False):
    async def create_pool(*args, **kwargs):
        await asyncio.sleep(0)  # force cold callers to interleave inside creation
        created.append(FakePool(close_hangs=hang))
        return created[-1]

    return create_pool


# ── decision-service persistence ───────────────────────────────────────────


@pytest.fixture
def decision(monkeypatch):
    import asyncpg

    mod = _load("_decision_persistence_pool_audit", os.path.join(DECISION, "persistence.py"))
    created: list[FakePool] = []
    monkeypatch.setattr(mod, "database_url", lambda: "postgresql://decision@db/decision")
    monkeypatch.setattr(asyncpg, "create_pool", _fake_create_pool(created))
    yield mod, created
    sys.modules.pop("_decision_persistence_pool_audit", None)


def test_decision_concurrent_cold_acquire_creates_exactly_one_pool(decision):
    mod, created = decision

    async def scenario():
        conns = await asyncio.gather(*(mod.acquire_connection() for _ in range(6)))
        return {id(conn._pool) for conn in conns}

    pools = asyncio.run(scenario())
    assert len(created) == 1, f"six cold callers opened {len(created)} pools"
    assert pools == {id(created[0])}


def test_decision_close_pools_closes_and_restart_creates_fresh_one(decision):
    mod, created = decision

    async def run_once():
        await asyncio.gather(mod.acquire_connection(), mod.acquire_connection())
        await mod.close_pools()

    asyncio.run(run_once())
    assert len(created) == 1 and created[0].closed and not created[0].terminated
    assert mod._POOLS == {}
    asyncio.run(run_once())
    assert len(created) == 2 and created[1] is not created[0] and created[1].closed


def test_decision_close_during_cold_creation_closes_the_new_pool(decision, monkeypatch):
    import asyncpg

    mod, created = decision
    release = asyncio.Event()

    async def create_pool(*args, **kwargs):
        await release.wait()
        created.append(FakePool())
        return created[-1]

    monkeypatch.setattr(asyncpg, "create_pool", create_pool)

    async def scenario():
        getter = asyncio.create_task(mod.acquire_connection())
        await asyncio.sleep(0)  # the getter now holds the lock inside create_pool
        closer = asyncio.create_task(mod.close_pools())
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(getter, closer)

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))
    assert len(created) == 1 and created[0].closed
    assert mod._POOLS == {}


def test_decision_close_timeout_falls_back_to_terminate(decision, monkeypatch):
    import asyncpg

    mod, created = decision
    monkeypatch.setattr(asyncpg, "create_pool", _fake_create_pool(created, hang=True))
    monkeypatch.setattr(mod, "_POOL_CLOSE_TIMEOUT_SECONDS", 0.01, raising=False)

    async def scenario():
        await mod.acquire_connection()
        await mod.close_pools()

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))
    assert len(created) == 1 and created[0].terminated and not created[0].closed


# ── vegetation PostgresAnomalyStore ────────────────────────────────────────


@pytest.fixture
def anomaly_store(monkeypatch):
    mod = _load(
        "_anomaly_store_pg_pool_audit",
        os.path.join(VEGETATION, "anomaly_store_pg.py"),
        deps={"anomaly_store": os.path.join(VEGETATION, "anomaly_store.py")},
    )
    created: list[FakePool] = []
    monkeypatch.setattr(mod.asyncpg, "create_pool", _fake_create_pool(created))
    yield mod, created
    sys.modules.pop("_anomaly_store_pg_pool_audit", None)


def test_anomaly_store_concurrent_cold_get_pool_creates_exactly_one_pool(anomaly_store):
    mod, created = anomaly_store
    store = mod.PostgresAnomalyStore("postgresql://veg@db/veg")

    async def scenario():
        return await asyncio.gather(*(store._get_pool() for _ in range(6)))

    pools = asyncio.run(scenario())
    assert len(created) == 1, f"six cold callers opened {len(created)} pools"
    assert all(pool is created[0] for pool in pools)


def test_anomaly_store_close_and_restart_creates_fresh_pool(anomaly_store):
    mod, created = anomaly_store
    store = mod.PostgresAnomalyStore("postgresql://veg@db/veg")

    async def run_once():
        await asyncio.gather(store._get_pool(), store._get_pool())
        await store.close()

    asyncio.run(run_once())
    assert len(created) == 1 and created[0].closed and store._pool is None
    asyncio.run(run_once())
    assert len(created) == 2 and created[1].closed


def test_anomaly_store_close_during_cold_creation_closes_the_new_pool(anomaly_store, monkeypatch):
    mod, created = anomaly_store
    store = mod.PostgresAnomalyStore("postgresql://veg@db/veg")
    release = asyncio.Event()

    async def create_pool(*args, **kwargs):
        await release.wait()
        created.append(FakePool())
        return created[-1]

    monkeypatch.setattr(mod.asyncpg, "create_pool", create_pool)

    async def scenario():
        getter = asyncio.create_task(store._get_pool())
        await asyncio.sleep(0)
        closer = asyncio.create_task(store.close())
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(getter, closer)

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))
    assert len(created) == 1 and created[0].closed and store._pool is None


def test_anomaly_store_close_timeout_falls_back_to_terminate(anomaly_store, monkeypatch):
    mod, created = anomaly_store
    monkeypatch.setattr(mod.asyncpg, "create_pool", _fake_create_pool(created, hang=True))
    monkeypatch.setattr(mod, "_POOL_CLOSE_TIMEOUT_SECONDS", 0.01, raising=False)
    store = mod.PostgresAnomalyStore("postgresql://veg@db/veg")

    async def scenario():
        await store._get_pool()
        await store.close()

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))
    assert created[0].terminated and not created[0].closed and store._pool is None


# ── platform app + jobs pools ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def platform_main():
    added = PLATFORM not in sys.path
    if added:
        sys.path.insert(0, PLATFORM)
    pytest.importorskip("fastapi")
    import api.main as main_mod

    yield main_mod
    if added and PLATFORM in sys.path:
        sys.path.remove(PLATFORM)


def test_platform_shutdown_closes_the_jobs_pool_too(platform_main, monkeypatch):
    app_pool, jobs_pool = FakePool(), FakePool()
    monkeypatch.setattr(platform_main, "_DB_POOL", app_pool)
    monkeypatch.setattr(platform_main, "_JOBS_POOL", jobs_pool)

    asyncio.run(platform_main._close_db_pool())
    assert app_pool.closed, "app pool left open"
    assert jobs_pool.closed, "jobs pool left open at shutdown"
    assert platform_main._DB_POOL is None and platform_main._JOBS_POOL is None


def test_platform_shutdown_terminates_a_hung_pool_and_still_closes_the_other(
    platform_main, monkeypatch
):
    app_pool, jobs_pool = FakePool(), FakePool(close_hangs=True)
    monkeypatch.setattr(platform_main, "_DB_POOL", app_pool)
    monkeypatch.setattr(platform_main, "_JOBS_POOL", jobs_pool)
    shutdown = sys.modules["shared.pool_shutdown"]  # the bounded close lives outside main.py
    monkeypatch.setattr(shutdown, "POOL_CLOSE_TIMEOUT_SECONDS", 0.01)

    asyncio.run(asyncio.wait_for(platform_main._close_db_pool(), timeout=5))
    assert jobs_pool.terminated and not jobs_pool.closed
    assert app_pool.closed


# ── lifespan wiring (own process per service: deployment-local imports) ────

_LIFESPAN_PRELUDE = """
import asyncio, json, sys
import asyncpg

created = []

class FakePool:
    closed = terminated = False
    async def acquire(self):
        return object()
    async def release(self, conn):
        return None
    async def close(self):
        self.closed = True
    def terminate(self):
        self.terminated = True

async def create_pool(*args, **kwargs):
    await asyncio.sleep(0)
    created.append(FakePool())
    return created[-1]

asyncpg.create_pool = create_pool
"""


def _run_in_service(service_dir: str, body: str) -> dict:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([service_dir, ROOT])}
    env.pop("DATABASE_URL", None)
    proc = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(_LIFESPAN_PRELUDE) + textwrap.dedent(body)],
        cwd=service_dir,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_decision_lifespan_shutdown_closes_the_pool():
    result = _run_in_service(
        DECISION,
        """
        import main, persistence
        persistence.database_url = lambda: "postgresql://decision@db/decision"

        async def scenario():
            async with main.lifespan(main.app):
                await asyncio.gather(*(persistence.acquire_connection() for _ in range(3)))

        asyncio.run(scenario())
        print(json.dumps({"created": len(created), "closed": [p.closed for p in created],
                          "left": len(persistence._POOLS)}))
        """,
    )
    assert result == {"created": 1, "closed": [True], "left": 0}


def test_vegetation_lifespan_shutdown_closes_the_anomaly_pool():
    result = _run_in_service(
        VEGETATION,
        """
        import os
        os.environ["VEGETATION_ANOMALY_STORE"] = "postgres"
        os.environ["DATABASE_URL"] = "postgresql://veg@db/veg"
        import main, anomaly_runtime

        async def scenario():
            async with main.lifespan(main.app):
                backend = anomaly_runtime.store._backend
                await asyncio.gather(*(backend._get_pool() for _ in range(3)))

        asyncio.run(scenario())
        print(json.dumps({"created": len(created), "closed": [p.closed for p in created]}))
        """,
    )
    assert result == {"created": 1, "closed": [True]}
