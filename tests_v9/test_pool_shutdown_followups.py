"""Bounded, single-owner pool shutdown for the follow-ups listed by the create_pool audit (#1277).

``test_pool_single_owner_audit.py`` fixed three owners; these are the rest:

  * erp-bridge (``services/odoo-bridge``): the lifespan closed the pool while the sync loop
    still ran (and held connections), closed without a bound and left ``_pool`` set; the
    lazy ``get_pool()`` fallback opened an unowned pool per concurrent cold caller;
  * actuator-service: the MQTT and dispatch loops ran on while the pool closed, unbounded;
  * auth and soil-service: ``close()`` without a bound, so a held connection hung shutdown;
  * market MCP: the same unbounded close, plus the same unowned lazy ``get_pool()`` fallback;
  * ``shared/helpers.py``: ``init_db`` (and the ``get_pool``/``service_lifespan``/
    ``create_app`` chain above it) had no caller anywhere, so it is gone.

Each lifespan runs in its own process, laid out as its Dockerfile's ``COPY`` lines build
``/app`` (so the image really carries ``shared/pool_shutdown.py``), with a fake pool that
records whether a background task was still running when ``close()`` began.
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]

_RUNNER = textwrap.dedent(
    """
    import asyncio, importlib, json, sys, types

    app_dir, spec = sys.argv[1], json.loads(sys.argv[2])
    sys.path.insert(0, app_dir)
    try:
        import aiomqtt  # noqa: F401
    except ModuleNotFoundError:  # left out of the test env on purpose; unused before connect
        sys.modules["aiomqtt"] = types.SimpleNamespace(Client=object)

    import asyncpg

    created, background = [], []


    class FakePool:
        def __init__(self):
            self.closed = self.terminated = False
            self.running_at_close = None

        def acquire(self):
            class _Ctx:
                async def __aenter__(self):
                    return object()

                async def __aexit__(self, *exc):
                    return False

            return _Ctx()

        async def close(self):
            self.running_at_close = sum(not t.done() for t in background)
            if spec.get("hang"):
                await asyncio.Event().wait()
            self.closed = True

        def terminate(self):
            self.terminated = True


    async def create_pool(*args, **kwargs):
        await asyncio.sleep(0)
        created.append(FakePool())
        return created[-1]


    asyncpg.create_pool = create_pool

    import shared.db_role_guard as role_guard


    async def _no_role_check(*args, **kwargs):
        return None


    role_guard.assert_db_role_rls_safe = _no_role_check

    cancelled = []


    async def hold_forever(*args, **kwargs):
        background.append(asyncio.current_task())
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(True)
            raise


    def pool_ref():
        mod, _, attr = spec["pool"].rpartition(":")
        return getattr(sys.modules[mod], attr)


    module = importlib.import_module(spec["module"])
    exec(spec.get("setup", ""))
    if spec.get("bound"):
        import shared.pool_shutdown as shutdown

        shutdown.POOL_CLOSE_TIMEOUT_SECONDS = spec["bound"]


    async def scenario():
        if spec.get("body"):
            return await eval(spec["body"])
        app = module.app
        async with app.router.lifespan_context(app):
            for _ in range(3):
                await asyncio.sleep(0)  # let the background loops start
        return None


    try:
        value = asyncio.run(asyncio.wait_for(scenario(), 5))
        outcome = "returned"
    except BaseException as exc:  # noqa: BLE001
        value, outcome = None, "died:" + type(exc).__name__
    print("RESULT " + json.dumps({
        "outcome": outcome,
        "value": value,
        "created": len(created),
        "closed": [p.closed for p in created],
        "terminated": [p.terminated for p in created],
        "running_at_close": [p.running_at_close for p in created],
        "background": len(background),
        "cancelled": len(cancelled),
        "pool_left": pool_ref() is not None,
    }, default=repr), flush=True)
    """
)

_IMAGES: dict[str, Path] = {}


def _assemble_image(dockerfile: str, base: Path) -> Path:
    """Build ``/app`` exactly as the Dockerfile's ``COPY`` lines do (no more)."""
    if dockerfile in _IMAGES:
        return _IMAGES[dockerfile]
    app = base / re.sub(r"\W", "_", dockerfile) / "app"
    app.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "tests", "*.pyc", "node_modules")
    for raw in (ROOT / dockerfile).read_text(encoding="utf-8").splitlines():
        parts = raw.split()
        if len(parts) < 3 or parts[0] != "COPY" or any(p.startswith("--") for p in parts):
            continue
        *srcs, dst = parts[1:]
        if not dst.startswith("/app"):
            continue
        target = app / dst[len("/app") :].lstrip("/")
        for src in srcs:
            source = ROOT / src
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True, ignore=ignore)
            else:
                dest = target / source.name if dst.endswith("/") else target
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
    _IMAGES[dockerfile] = app
    return app


@pytest.fixture(scope="module")
def image_root(tmp_path_factory):
    pytest.importorskip("fastapi")
    return tmp_path_factory.mktemp("pool_shutdown_images")


def _run(image_root: Path, dockerfile: str, spec: dict, env: dict[str, str]) -> dict:
    app = _assemble_image(dockerfile, image_root)
    runner = image_root / "run_lifespan.py"
    runner.write_text(_RUNNER, encoding="utf-8")
    base_env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "DATABASE_URL"}}
    base_env.update(
        {
            "PYTHONPATH": str(app),
            "SAHOOL_ENV": "development",
            "JWT_SECRET": "test_secret_min_32_chars_for_sahool_v9",
            "REDIS_URL": "redis://127.0.0.1:1/0",
            **env,
        }
    )
    proc = subprocess.run(
        [sys.executable, str(runner), str(app), json.dumps(spec)],
        cwd=app,
        env=base_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    lines = [line for line in proc.stdout.splitlines() if line.startswith("RESULT ")]
    assert lines, proc.stderr[-3000:]
    return json.loads(lines[-1][len("RESULT ") :])


DSN = "postgresql://sahool_app:unused@127.0.0.1:1/sahool"

ERP = (
    "services/odoo-bridge/Dockerfile",
    {"module": "main", "pool": "erp_runtime:_pool"},
    {"SAHOOL_DB_URL": DSN, "DATABASE_URL": DSN, "ERP_PROVIDER": "none"},
)
_ERP_SETUP = """
async def _no_migrations():
    return None
module._run_migrations = _no_migrations
module.periodic_sync = hold_forever
"""

ACTUATOR = (
    "services/actuator-service/Dockerfile",
    {"module": "actuator_runtime", "pool": "actuator_runtime:_pool"},
    {"DATABASE_URL": DSN, "ACTUATOR_MODE": "simulation"},
)
_ACTUATOR_SETUP = """
module.mqtt_sensor_listener = hold_forever
module.dispatch_consumer_loop = hold_forever
module._dispatch_consumer_enabled = lambda value: True
"""

AUTH = (
    "services/auth/Dockerfile",
    {"module": "main", "pool": "main:_pool"},
    {"DATABASE_URL": DSN},
)
_AUTH_SETUP = """
async def _no_admin():
    return None
module._ensure_admin_user = _no_admin
"""

SOIL = (
    "services/soil-service/Dockerfile",
    {"module": "main", "pool": "main:_pool"},
    {"DATABASE_URL": DSN, "SOIL_PROJECTION_WORKER_ENABLED": "false"},
)

MARKET = (
    "services/mcp_servers/Dockerfile",
    {"module": "market_server", "pool": "market_server:_pool"},
    {"DATABASE_URL": DSN},
)


def _case(case, image_root, **extra):
    dockerfile, spec, env = case
    return _run(image_root, dockerfile, {**spec, **extra}, env)


# ── erp-bridge (odoo-bridge) ───────────────────────────────────────────────


def test_erp_bridge_stops_the_sync_loop_before_closing_the_pool(image_root):
    result = _case(ERP, image_root, setup=_ERP_SETUP)
    assert result["outcome"] == "returned", result
    assert result["background"] == 1 and result["cancelled"] == 1, (
        f"sync loop still running after shutdown: {result}"
    )
    assert result["running_at_close"] == [0], f"pool closed while the sync loop still ran: {result}"
    assert result["closed"] == [True] and not result["pool_left"], result


def test_erp_bridge_close_is_bounded_and_terminates(image_root):
    result = _case(ERP, image_root, setup=_ERP_SETUP, hang=True, bound=0.05)
    assert result["outcome"] == "returned", f"shutdown hung on close(): {result}"
    assert result["terminated"] == [True] and result["closed"] == [False], result
    assert not result["pool_left"], result


def test_erp_bridge_get_pool_never_opens_an_unowned_pool(image_root):
    body = "asyncio.gather(*(sys.modules['erp_runtime'].get_pool() for _ in range(6)))"
    result = _case(ERP, image_root, body=body)
    assert result["outcome"] == "returned", result
    assert result["created"] == 0, (
        f"six cold get_pool() callers opened {result['created']} pools no one closes"
    )
    assert result["value"] == [None] * 6


# ── actuator-service ───────────────────────────────────────────────────────


def test_actuator_stops_mqtt_and_dispatch_loops_before_closing_the_pool(image_root):
    result = _case(ACTUATOR, image_root, setup=_ACTUATOR_SETUP)
    assert result["outcome"] == "returned", result
    assert result["background"] == 2 and result["cancelled"] == 2, (
        f"MQTT/dispatch loops still running after shutdown: {result}"
    )
    assert result["running_at_close"] == [0], (
        f"pool closed while the MQTT/dispatch loops still ran: {result}"
    )
    assert result["closed"] == [True] and not result["pool_left"], result


def test_actuator_close_is_bounded_and_terminates(image_root):
    result = _case(ACTUATOR, image_root, setup=_ACTUATOR_SETUP, hang=True, bound=0.05)
    assert result["outcome"] == "returned", f"shutdown hung on close(): {result}"
    assert result["terminated"] == [True] and not result["pool_left"], result


# ── auth, soil-service ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "case,setup", [(AUTH, _AUTH_SETUP), (SOIL, "")], ids=["auth", "soil-service"]
)
def test_close_is_bounded_and_terminates(image_root, case, setup):
    result = _case(case, image_root, setup=setup, hang=True, bound=0.05)
    assert result["outcome"] == "returned", f"shutdown hung on close(): {result}"
    assert result["terminated"] == [True] and result["closed"] == [False], result
    assert not result["pool_left"], result


@pytest.mark.parametrize(
    "case,setup", [(AUTH, _AUTH_SETUP), (SOIL, "")], ids=["auth", "soil-service"]
)
def test_clean_shutdown_still_closes(image_root, case, setup):
    result = _case(case, image_root, setup=setup)
    assert result["outcome"] == "returned", result
    assert result["closed"] == [True] and result["terminated"] == [False], result
    assert not result["pool_left"], result


# ── market MCP ─────────────────────────────────────────────────────────────

_MARKET_BOUND = "module._POOL_CLOSE_TIMEOUT_SECONDS = 0.05\n"


def test_market_close_is_bounded_and_terminates(image_root):
    result = _case(MARKET, image_root, setup=_MARKET_BOUND, hang=True)
    assert result["outcome"] == "returned", f"shutdown hung on close(): {result}"
    assert result["terminated"] == [True] and result["closed"] == [False], result
    assert not result["pool_left"], result


def test_market_clean_shutdown_still_closes(image_root):
    result = _case(MARKET, image_root)
    assert result["outcome"] == "returned", result
    assert result["closed"] == [True] and not result["pool_left"], result


def test_market_get_pool_never_opens_an_unowned_pool(image_root):
    body = "asyncio.gather(*(module.get_pool() for _ in range(6)), return_exceptions=True)"
    result = _case(MARKET, image_root, body=f"_status({body})", setup=_MARKET_STATUS)
    assert result["outcome"] == "returned", result
    assert result["created"] == 0, (
        f"six cold get_pool() callers opened {result['created']} pools no one closes"
    )
    assert result["value"] == [503] * 6


_MARKET_STATUS = """
async def _status(gathered):
    return [getattr(item, "status_code", repr(item)) for item in await gathered]
"""


# ── shared.pool_shutdown.cancel_tasks_bounded ──────────────────────────────


def test_cancel_tasks_bounded_cancels_awaits_and_bounds(monkeypatch):
    sys.path.insert(0, str(ROOT))
    try:
        from shared import pool_shutdown
    finally:
        sys.path.remove(str(ROOT))
    monkeypatch.setattr(pool_shutdown, "POOL_CLOSE_TIMEOUT_SECONDS", 0.05)

    release = asyncio.Event()

    async def stubborn():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()  # ignores the first cancel: the bound must still return

    async def failed():
        raise RuntimeError("loop died earlier")

    async def scenario():
        loop_task = asyncio.create_task(asyncio.Event().wait())
        stuck = asyncio.create_task(stubborn())
        dead = asyncio.create_task(failed())
        await asyncio.sleep(0)
        try:
            await pool_shutdown.cancel_tasks_bounded([loop_task, None, stuck, dead], "test")
            return (loop_task.cancelled(), stuck.done(), dead.done())
        finally:
            release.set()
            await asyncio.gather(loop_task, stuck, dead, return_exceptions=True)

    assert asyncio.run(asyncio.wait_for(scenario(), 5)) == (True, False, True)


# ── shared/helpers.py: the unused init_db chain is gone ────────────────────

_DEAD = {"init_db", "get_pool", "get_db_pool", "close_pool", "service_lifespan", "create_app"}


def test_shared_helpers_has_no_unowned_lazy_pool():
    tree = ast.parse((ROOT / "shared" / "helpers.py").read_text(encoding="utf-8"))
    defined = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    } | {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign | ast.AnnAssign)
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    }
    assert not defined & (_DEAD | {"_db_pool"}), sorted(defined & (_DEAD | {"_db_pool"}))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "create_pool"
    ]
    assert not calls, "shared/helpers.py opens an asyncpg pool again"
