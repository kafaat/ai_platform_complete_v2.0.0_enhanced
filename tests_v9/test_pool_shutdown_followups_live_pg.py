"""Live-PG proof of the pool shutdown follow-ups, measured in backends.

``test_pool_shutdown_followups.py`` proves the order and the bound with a fake pool. Here
each service's real lifespan runs (in its own process, laid out as its Dockerfile builds
``/app``) against a real PostgreSQL, with a real asyncpg pool whose connections carry a unique
``application_name``. A connection is held across shutdown, as in production:

  * erp-bridge: by the background sync loop. The
    lifespan must cancel the loop first, so ``close()`` finishes cleanly, well inside the bound;
  * auth, soil-service and market MCP: by an in-flight request that never returns. ``close()``
    would wait on it for ever; the bound must terminate the pool instead.

Either way ``pg_stat_activity`` must show zero backends for that name once the lifespan has
exited, measured from inside the process before it ends (process exit would close them anyway).

Runs with ``pytest -m integration``. With ``HIL_CERTIFICATION_REQUIRED=1`` a missing
database is a failure, not a skip (as in ``test_pool_single_owner_live_pg.py``).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOUND = 1.0  # the production 5 s bound, shortened for the run

_RUNNER = textwrap.dedent(
    """
    import asyncio, importlib, json, sys, time, types

    app_dir, spec = sys.argv[1], json.loads(sys.argv[2])
    sys.path.insert(0, app_dir)
    try:
        import aiomqtt  # noqa: F401
    except ModuleNotFoundError:
        sys.modules["aiomqtt"] = types.SimpleNamespace(Client=object)

    import asyncpg
    import shared.db_role_guard as role_guard


    async def _no_role_check(*args, **kwargs):
        return None  # the disposable role may be a superuser; this measures pool ownership


    role_guard.assert_db_role_rls_safe = _no_role_check
    held = asyncio.Event()


    def pool_ref():
        mod, _, attr = spec["pool"].rpartition(":")
        return getattr(sys.modules[mod], attr)


    async def hold_connection(*args, **kwargs):
        async with pool_ref().acquire() as conn:
            await conn.fetchval("SELECT 1")
            held.set()
            await asyncio.Event().wait()


    async def backends():
        conn = await asyncpg.connect(spec["probe_url"], statement_cache_size=0)
        try:
            return await conn.fetchval(
                "SELECT count(*) FROM pg_stat_activity WHERE application_name = $1",
                spec["name"],
            )
        finally:
            await conn.close()


    module = importlib.import_module(spec["module"])
    exec(spec.get("setup", ""))
    import shared.pool_shutdown as shutdown

    shutdown.POOL_CLOSE_TIMEOUT_SECONDS = spec["bound"]
    if hasattr(module, "_POOL_CLOSE_TIMEOUT_SECONDS"):
        module._POOL_CLOSE_TIMEOUT_SECONDS = spec["bound"]
    result = {}


    async def scenario():
        app = module.app
        request = None
        async with app.router.lifespan_context(app):
            if spec["holder"] == "request":
                request = asyncio.create_task(hold_connection())
            await asyncio.wait_for(held.wait(), 10)
            result["during"] = await backends()
            started = time.monotonic()
        result["shutdown_seconds"] = round(time.monotonic() - started, 2)
        result["pool_left"] = pool_ref() is not None
        deadline = time.monotonic() + 5
        result["after"] = await backends()
        while result["after"] and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
            result["after"] = await backends()
        if request is not None:
            request.cancel()


    try:
        asyncio.run(asyncio.wait_for(scenario(), 20))
        result["outcome"] = "returned"
    except BaseException as exc:  # noqa: BLE001
        result["outcome"] = "died:" + type(exc).__name__
    print("RESULT " + json.dumps(result), flush=True)
    """
)


def _database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL", "")
    if url:
        return url
    message = "live pool certificate requires explicit TEST_DATABASE_URL"
    if os.getenv("HIL_CERTIFICATION_REQUIRED") == "1":
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


def _require_database(url: str) -> None:
    import asyncio

    import asyncpg

    async def probe():
        conn = await asyncpg.connect(url, statement_cache_size=0)
        await conn.close()

    try:
        asyncio.run(asyncio.wait_for(probe(), 10.0))
    except Exception as exc:  # noqa: BLE001 - the database is the precondition
        message = f"live pool database unavailable: {type(exc).__name__}"
        if os.getenv("HIL_CERTIFICATION_REQUIRED") == "1":
            pytest.fail(message, pytrace=False)
        pytest.skip(message)


def _with_application_name(url: str, name: str) -> str:
    parts = urlsplit(url)
    query = "&".join(q for q in (parts.query, urlencode({"application_name": name})) if q)
    return urlunsplit(parts._replace(query=query))


def _assemble_image(dockerfile: str, base: Path) -> Path:
    """Build ``/app`` exactly as the Dockerfile's ``COPY`` lines do (no more)."""
    app = base / re.sub(r"\W", "_", dockerfile) / "app"
    if app.exists():
        return app
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
    return app


_ERP_SETUP = """
async def _no_migrations():
    return None
module._run_migrations = _no_migrations
module.periodic_sync = hold_connection
"""
_AUTH_SETUP = """
async def _no_admin():
    return None
module._ensure_admin_user = _no_admin
"""

CASES = {
    "erp-bridge": (
        "services/odoo-bridge/Dockerfile",
        {"module": "main", "pool": "erp_runtime:_pool", "setup": _ERP_SETUP},
        ("SAHOOL_DB_URL", "DATABASE_URL"),
        {"ERP_PROVIDER": "none"},
        "background",
    ),
    "auth": (
        "services/auth/Dockerfile",
        {"module": "main", "pool": "main:_pool", "setup": _AUTH_SETUP},
        ("DATABASE_URL",),
        {"REDIS_URL": "redis://127.0.0.1:1/0"},
        "request",
    ),
    "soil-service": (
        "services/soil-service/Dockerfile",
        {"module": "main", "pool": "main:_pool"},
        ("DATABASE_URL",),
        {"SOIL_PROJECTION_WORKER_ENABLED": "false"},
        "request",
    ),
    "market-mcp": (
        "services/mcp_servers/Dockerfile",
        {"module": "market_server", "pool": "market_server:_pool"},
        ("DATABASE_URL",),
        {},
        "request",
    ),
}


@pytest.fixture(scope="module")
def image_root(tmp_path_factory):
    pytest.importorskip("fastapi")
    pytest.importorskip("asyncpg")
    return tmp_path_factory.mktemp("pool_shutdown_live_images")


@pytest.mark.integration
@pytest.mark.parametrize("service", sorted(CASES))
def test_shutdown_leaves_no_backends_with_a_connection_held(image_root, service):
    url = _database_url()
    _require_database(url)
    dockerfile, spec, url_vars, extra_env, holder = CASES[service]
    name = f"sahool-{service}-shutdown-{uuid.uuid4().hex[:10]}"
    app = _assemble_image(dockerfile, image_root)
    runner = image_root / "run_lifespan_live.py"
    runner.write_text(_RUNNER, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "DATABASE_URL"}}
    env.update(
        {
            "PYTHONPATH": str(app),
            "SAHOOL_ENV": "development",
            "JWT_SECRET": "test_secret_min_32_chars_for_sahool_v9",
            "SAHOOL_STARTUP_CONNECT_DEADLINE_SECONDS": "0",
            **{var: _with_application_name(url, name) for var in url_vars},
            **extra_env,
        }
    )
    payload = {**spec, "name": name, "probe_url": url, "holder": holder, "bound": BOUND}
    proc = subprocess.run(
        [sys.executable, str(runner), str(app), json.dumps(payload)],
        cwd=app,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    lines = [line for line in proc.stdout.splitlines() if line.startswith("RESULT ")]
    assert lines, proc.stderr[-3000:]
    result = json.loads(lines[-1][len("RESULT ") :])
    assert result["outcome"] == "returned", f"shutdown hung on the held connection: {result}"
    assert result["during"] >= 1, result
    assert result["after"] == 0, f"{service} left backends open after shutdown: {result}"
    assert not result["pool_left"], result
    if holder == "background":
        # The loop was cancelled first, so close() finished cleanly instead of timing out.
        assert result["shutdown_seconds"] < BOUND, result
