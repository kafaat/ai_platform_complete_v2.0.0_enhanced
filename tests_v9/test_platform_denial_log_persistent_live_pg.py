"""The security denial log is durable: it survives a restart and stays tenant-scoped (#1427).

Owner decision of 2026-11-14: ``require_permission`` denials were kept only in the
in-process ring buffer of ``core.tenant_audit``, so a restart (or a second worker) lost them.
They are now written to the existing ``audit_log`` table (owned and written by
sahool-platform, append-only, RLS forced) by ``DenialStore``: an in-memory append on the
request path and a background task that writes batches. This file proves it on a migrated
PostgreSQL under a NOBYPASSRLS role, over the real platform app:

* two tenants produce real 403 denials; unattributed events are recorded the way in-process
  diagnostics record them; the background writer stores them, with no tenant for the
  unattributed ones (read back through the superuser admin DSN);
* a **new Python process** (a restart: empty ring buffer) builds the app, binds the store with
  the lifespan's own helper and reads the endpoint for each tenant: each tenant reads only its
  own denials from ``source: db``, never the unattributed ones, and ``limit`` applies after
  the tenant filter;
* with the database unavailable, a denied request is still answered 403 (never 500), the
  failed write is counted, and the endpoint falls back to the ring buffer with
  ``source: memory``.

``audit_log`` is append-only (a trigger blocks DELETE), so the rows stay; every run uses fresh
random tenants. Run: ``TEST_DATABASE_URL=… TEST_DATABASE_ADMIN_URL=… pytest -m integration
tests_v9/test_platform_denial_log_persistent_live_pg.py``.
``AUTH_ADMIN_SCOPE_CERTIFICATION_REQUIRED=1`` turns every skip into a failure.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import textwrap
import time
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

_CERTIFICATION_REQUIRED = os.getenv("AUTH_ADMIN_SCOPE_CERTIFICATION_REQUIRED") == "1"
DSN = os.getenv("TEST_DATABASE_URL") or ""
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
_ENDPOINT = "/api/v1/admin/security/denials"
_SECRET = os.getenv("JWT_SECRET") or "p" * 48


async def _probe() -> str:
    if not DSN or not ADMIN_DSN:
        return "needs TEST_DATABASE_URL (restricted role) and TEST_DATABASE_ADMIN_URL"
    try:
        import asyncpg
        import fastapi  # noqa: F401
        import httpx  # noqa: F401
    except ImportError as exc:
        return f"missing dependency: {exc}"
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        if await conn.fetchval("SELECT to_regclass('public.audit_log')") is None:
            return "schema not migrated (audit_log missing)"
        bypass = await conn.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        if bypass:
            return "TEST_DATABASE_URL role bypasses RLS; the scope would not be measured"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
if _WHY and _CERTIFICATION_REQUIRED:
    raise RuntimeError(f"AUTH_ADMIN_SCOPE_CERTIFICATION_REQUIRED=1 but: {_WHY}")
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in {"REDIS_URL", "DENYLIST_REDIS_URL"}}
    env.update({"SAHOOL_ENV": "development", "SAHOOL_JWT_SECRET": _SECRET})
    env.pop("JWT_PUBLIC_KEY", None)
    env.pop("DATABASE_URL", None)
    return env


@pytest.fixture(scope="module")
def platform():
    mp = pytest.MonkeyPatch()
    mp.setenv("SAHOOL_ENV", "development")
    mp.setenv("SAHOOL_JWT_SECRET", _SECRET)
    for key in ("REDIS_URL", "DENYLIST_REDIS_URL", "JWT_PUBLIC_KEY", "DATABASE_URL"):
        mp.delenv(key, raising=False)
    mp.syspath_prepend(str(PLATFORM))
    try:
        import api.main as main
        from core.tenant_audit import AUDIT, DENIAL_STORE

        yield {"m": main, "audit": AUDIT, "store": DENIAL_STORE, "mp": mp}
    finally:
        mp.undo()


def _token(main, tenant: str, role: str) -> tuple[str, dict]:
    from core.canonical_schemas import UserRole, UserSchema

    user_id = f"den-{role}-{uuid.uuid4().hex[:8]}"
    user = UserSchema(user_id=user_id, tenant_id=tenant, role=UserRole(role), name_ar="تدقيق")
    return user_id, {"Authorization": f"Bearer {main.create_token(user)}"}


def _client(main):
    import httpx

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://t")


async def _admin_rows(tenants: list[str], marker: str) -> dict:
    import asyncpg

    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        per_tenant = {
            t: await conn.fetchval(
                "SELECT count(*) FROM audit_log WHERE tenant_id = $1::uuid "
                "AND action = 'denial:permission'",
                t,
            )
            for t in tenants
        }
        unattributed = await conn.fetch(
            "SELECT tenant_id, action FROM audit_log WHERE action LIKE 'denial:%' "
            "AND details LIKE $1",
            f"%{marker}%",
        )
    finally:
        await conn.close()
    return {"per_tenant": per_tenant, "unattributed": [dict(r) for r in unattributed]}


# The restarted process: a fresh interpreter, so the ring buffer is empty. It binds the store
# with the lifespan's own helper (main._start_denial_store) and reads as each tenant's auditor.
_RESTARTED = textwrap.dedent(
    """
    import asyncio, json, sys
    import asyncpg, httpx
    import api.main as main
    from core.canonical_schemas import UserRole, UserSchema
    from core.tenant_audit import AUDIT

    dsn, tenants = sys.argv[1], json.loads(sys.argv[2])

    def hdr(tenant, role):
        user = UserSchema(user_id="auditor-" + role, tenant_id=tenant, role=UserRole(role),
                          name_ar="x")
        return {"Authorization": "Bearer " + main.create_token(user)}

    async def run():
        out = {"memory_before": len(AUDIT.recent()), "reads": {}, "limit1": {}}
        main._DB_POOL = await asyncpg.create_pool(dsn, min_size=1, max_size=3,
                                                  statement_cache_size=0)
        main._start_denial_store()
        transport = httpx.ASGITransport(app=main.app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
                for tenant in tenants:
                    out["reads"][tenant] = {}
                    for role in ("owner", "manager", "platform_admin"):
                        r = await c.get(%(endpoint)r, headers=hdr(tenant, role))
                        out["reads"][tenant][role] = {"status": r.status_code, "body": r.json()}
                    r = await c.get(%(endpoint)r, headers=hdr(tenant, "owner"),
                                    params={"limit": 1})
                    out["limit1"][tenant] = r.json()
        finally:
            await main._stop_denial_store()
            await main._DB_POOL.close()
        out["memory_after"] = len(AUDIT.recent())
        print("RESULT " + json.dumps(out))

    asyncio.run(run())
    """
) % {"endpoint": _ENDPOINT}


def test_denials_survive_a_restart_and_each_tenant_reads_only_its_own(platform):
    import asyncpg

    main, audit, store = platform["m"], platform["audit"], platform["store"]
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    marker = uuid.uuid4().hex[:8]
    denied: dict[str, list[str]] = {tenant_a: [], tenant_b: []}

    async def first_run():
        pool = await asyncpg.create_pool(DSN, min_size=1, max_size=3, statement_cache_size=0)
        platform["mp"].setattr(main, "_DB_POOL", pool)
        store.interval = 0.2
        audit.clear()
        main._start_denial_store()  # the lifespan helper: binds to main._DB_POOL and starts
        try:
            async with _client(main) as c:
                for tenant, role, times in ((tenant_a, "viewer", 3), (tenant_b, "worker", 2)):
                    for _ in range(times):
                        user_id, hdr = _token(main, tenant, role)
                        r = await c.get(_ENDPOINT, headers=hdr)
                        assert r.status_code == 403, r.text[:200]
                        denied[tenant].append(user_id)
            audit.record("auth", user_id=f"system-{marker}")
            audit.record("permission", user_id=f"none-{marker}", tenant_id=None, action="x")
            audit.record("tenant_scope", user_id=f"empty-{marker}", tenant_id="", action="x")
            # The background writer, not a read, empties the queue.
            deadline = time.monotonic() + 15
            while store.stats()["pending"] and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
            stats = store.stats()
            assert stats["pending"] == 0 and stats["failed"] == 0, stats
        finally:
            await main._stop_denial_store()
            await pool.close()
            store.interval = 1.0

    asyncio.run(first_run())
    assert not store.bound

    stored = asyncio.run(_admin_rows([tenant_a, tenant_b], marker))
    assert stored["per_tenant"] == {tenant_a: 3, tenant_b: 2}, stored
    assert len(stored["unattributed"]) == 3, stored
    assert all(r["tenant_id"] is None for r in stored["unattributed"]), stored

    proc = subprocess.run(
        [sys.executable, "-c", _RESTARTED, DSN, json.dumps([tenant_a, tenant_b])],
        cwd=PLATFORM,
        env={**_env(), "PYTHONPATH": os.pathsep.join([str(PLATFORM), str(ROOT)])},
        capture_output=True,
        text=True,
        timeout=180,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]
    assert proc.returncode == 0 and lines, (proc.stdout[-2000:], proc.stderr[-4000:])
    out = json.loads(lines[-1][len("RESULT ") :])

    assert out["memory_before"] == 0 and out["memory_after"] == 0, out
    unattributed = {f"system-{marker}", f"none-{marker}", f"empty-{marker}"}
    for tenant, other in ((tenant_a, tenant_b), (tenant_b, tenant_a)):
        for role, res in out["reads"][tenant].items():
            assert res["status"] == 200, (role, res)
            body = res["body"]
            assert body["source"] == "db", (role, body)
            seen = body["denials"]
            assert {d["tenant_id"] for d in seen} == {tenant}, (role, seen[:3])
            got = [d["user_id"] for d in seen]
            assert got == list(reversed(denied[tenant])), (role, got)  # newest first
            assert not set(got) & (set(denied[other]) | unattributed), role
            assert {d["kind"] for d in seen} == {"permission"}
            assert body["summary"]["total"] == len(denied[tenant])
            assert body["summary"]["by_kind"] == {"permission": len(denied[tenant])}
            assert body["summary"]["last_at"] == seen[0]["at"]
            assert set(body["summary"]) == {"total", "buffer_capacity", "by_kind", "last_at"}
        # B's denials are newer than A's, so limit=1 for A proves the filter came first.
        newest = out["limit1"][tenant]["denials"]
        assert [d["user_id"] for d in newest] == [denied[tenant][-1]], newest


def test_a_database_outage_on_write_still_answers_403_and_reads_fall_back(platform):
    import asyncpg

    main, audit, store = platform["m"], platform["audit"], platform["store"]
    tenant = str(uuid.uuid4())
    result: dict = {}

    async def outage():
        pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2, statement_cache_size=0)
        await pool.close()  # the database is unreachable through the app's pool from here on
        platform["mp"].setattr(main, "_DB_POOL", pool)
        audit.clear()
        store.bind(lambda: main._DB_POOL)
        failed_before = store.failed
        try:
            async with _client(main) as c:
                user_id, hdr = _token(main, tenant, "viewer")
                denied = await c.get(_ENDPOINT, headers=hdr)
                result["denied_status"] = denied.status_code
                result["user_id"] = user_id
                result["flushed"] = await store.flush()
                result["failed"] = store.failed - failed_before
                _, auditor = _token(main, tenant, "owner")
                read = await c.get(_ENDPOINT, headers=auditor)
                result["read_status"] = read.status_code
                result["read"] = read.json()
        finally:
            store.unbind()

    asyncio.run(outage())
    assert result["denied_status"] == 403, result
    assert result["flushed"] == 0 and result["failed"] >= 1, result
    assert result["read_status"] == 200, result
    body = result["read"]
    assert body["source"] == "memory", body
    assert [d["user_id"] for d in body["denials"]] == [result["user_id"]]
    assert body["summary"]["total"] == 1

    stored = asyncio.run(_admin_rows([tenant], uuid.uuid4().hex))
    assert stored["per_tenant"] == {tenant: 0}, stored
