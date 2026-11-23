"""F-D01 on real PostgreSQL: the outbox backlog probe never reports a false zero under RLS.

``persistence.outbox_backlog`` counts pending ``decision_outbox_events`` rows for ``/readyz``.
The table is under FORCE ROW LEVEL SECURITY (decision-service migrations 033/034), so an unbound
role without BYPASSRLS sees no row at all and a plain ``count(*)`` reads ``0``. This file proves,
through the production code path (``DATABASE_URL`` → ``acquire_connection`` pool, nothing
replaced), what the probe answers per role:

* superuser → measured, with the pending rows of every tenant (non-pending rows excluded) and the
  age of the oldest;
* LOGIN NOSUPERUSER NOBYPASSRLS role → ``measured: false`` /
  ``row_level_security_hides_other_tenants`` — while the same role's own ``count(*)`` reads ``0``,
  the false zero the probe refuses to report;
* NOSUPERUSER BYPASSRLS auditor → measured, same count as the superuser;
* a BYPASSRLS role with no SELECT grant → ``query_failed`` with no error text;
* an empty outbox → measured ``0`` with no age, and the probe leaves every row as it found it.

Each module run creates its own database (every decision-service migration applied by the real
runner) and its own roles, and drops all of them. ``DECISION_OUTBOX_TEST_DATABASE_URL`` is a
loopback superuser DSN; without it the module is skipped, unless
``DECISION_OUTBOX_CERTIFICATION_REQUIRED=1``, where a missing database is a failure.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

pytestmark = pytest.mark.integration

DSN_ENV = "DECISION_OUTBOX_TEST_DATABASE_URL"
REQUIRED = os.getenv("DECISION_OUTBOX_CERTIFICATION_REQUIRED", "").strip() == "1"
ROOT_DSN = os.getenv(DSN_ENV, "").strip()
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
PASSWORD = "disposable_test_only"
RLS_REASON = "row_level_security_hides_other_tenants"
TENANT_A = "00000000-0000-0000-0000-00000000fd0a"
TENANT_B = "00000000-0000-0000-0000-00000000fd0b"
PENDING = 3  # two in tenant A, one in tenant B; plus one non-pending row the probe must skip
OLDEST_SECONDS = 3600


def _require_dsn() -> str:
    if not ROOT_DSN:
        if REQUIRED:
            pytest.fail(
                f"DECISION_OUTBOX_CERTIFICATION_REQUIRED=1 without {DSN_ENV}: the run claims a "
                "live outbox certification and has no database to certify on"
            )
        pytest.skip(f"requires real PostgreSQL: set {DSN_ENV} to a loopback superuser DSN")
    if urlsplit(ROOT_DSN).hostname not in LOOPBACK:
        pytest.fail(f"{DSN_ENV} must point at a loopback database: this test creates and drops")
    return ROOT_DSN


async def _connect(dsn: str):
    import asyncpg

    return await asyncpg.connect(dsn, statement_cache_size=0, timeout=10, command_timeout=20)


def _dsn(root: str, *, database: str, role: str | None = None) -> str:
    parts = urlsplit(root)
    netloc = parts.netloc
    if role is not None:
        host = parts.hostname if ":" not in (parts.hostname or "") else f"[{parts.hostname}]"
        netloc = f"{role}:{PASSWORD}@{host}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit(parts._replace(netloc=netloc, path=f"/{database}"))


@pytest.fixture(scope="module")
def outbox_db():
    root_dsn = _require_dsn()
    suffix = uuid4().hex[:12]
    dbname = f"decision_outbox_{suffix}"
    roles = {
        "app": f"decision_outbox_app_{suffix}",
        "auditor": f"decision_outbox_auditor_{suffix}",
        "noread": f"decision_outbox_noread_{suffix}",
    }
    attributes = {
        "app": "NOSUPERUSER NOBYPASSRLS",
        "auditor": "NOSUPERUSER BYPASSRLS",
        "noread": "NOSUPERUSER BYPASSRLS",
    }
    created: dict[str, bool] = {"db": False}
    admin_dsn = _dsn(root_dsn, database=dbname)

    async def _setup() -> None:
        root = await _connect(root_dsn)
        try:
            who = await root.fetchrow(
                "SELECT rolsuper, current_setting('server_version_num')::int AS version "
                "FROM pg_roles WHERE rolname = current_user"
            )
            assert who["rolsuper"], f"{DSN_ENV} must be a superuser: it creates roles and a db"
            assert who["version"] >= 160000, "this witness requires PostgreSQL 16 or later"
            await root.execute(f'CREATE DATABASE "{dbname}"')
            created["db"] = True
            for key, role in roles.items():
                await root.execute(
                    f"CREATE ROLE \"{role}\" LOGIN PASSWORD '{PASSWORD}' {attributes[key]} "
                    "NOCREATEDB NOCREATEROLE NOINHERIT"
                )
                created[role] = True
        finally:
            await root.close()

    async def _grant() -> None:
        admin = await _connect(admin_dsn)
        try:
            flags = await admin.fetchrow(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE oid = 'decision_outbox_events'::regclass"
            )
            assert tuple(flags) == (True, True), "033/034 must leave the outbox under FORCE RLS"
            for key in ("app", "auditor"):
                await admin.execute(f'GRANT SELECT ON decision_outbox_events TO "{roles[key]}"')
        finally:
            await admin.close()

    async def _teardown() -> None:
        root = await _connect(root_dsn)
        try:
            if created["db"]:
                await root.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
            for role in roles.values():
                if created.get(role):
                    await root.execute(f'DROP ROLE IF EXISTS "{role}"')
        finally:
            await root.close()

    try:
        asyncio.run(_setup())
        import migration_runner as runner

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("DATABASE_URL", admin_dsn)
            mp.setenv("DECISION_SERVICE_ALLOW_SCHEMA_CHANGE", "true")
            assert asyncio.run(runner.apply_migrations())["ok"]
        asyncio.run(_grant())
        yield SimpleNamespace(
            admin=admin_dsn,
            app=_dsn(root_dsn, database=dbname, role=roles["app"]),
            auditor=_dsn(root_dsn, database=dbname, role=roles["auditor"]),
            noread=_dsn(root_dsn, database=dbname, role=roles["noread"]),
            roles=roles,
        )
    finally:
        asyncio.run(_teardown())


async def _admin(dsn: str, sql: str, *args):
    conn = await _connect(dsn)
    try:
        return await conn.fetch(sql, *args)
    finally:
        await conn.close()


def _q(dsn: str, sql: str, *args):
    return asyncio.run(_admin(dsn, sql, *args))


def _empty(db) -> None:
    _q(db.admin, "DELETE FROM decision_outbox_events")


def _seed(db) -> None:
    """Three pending rows over two tenants (the oldest an hour old) and one non-pending row."""
    _empty(db)
    rows = [
        ("evt-a1", TENANT_A, "pending", f"now() - interval '{OLDEST_SECONDS} seconds'"),
        ("evt-a2", TENANT_A, "pending", "now()"),
        ("evt-b1", TENANT_B, "pending", "now() - interval '60 seconds'"),
        ("evt-b2", TENANT_B, "published", f"now() - interval '{2 * OLDEST_SECONDS} seconds'"),
    ]
    for event_id, tenant, status, created_at in rows:
        _q(
            db.admin,
            "INSERT INTO decision_outbox_events "
            "(event_id, tenant_id, event_type, aggregate_type, aggregate_id, status, created_at) "
            f"VALUES ($1, $2::uuid, 'CI_ONLY', 'ci_probe', $1, $3, {created_at})",
            event_id,
            tenant,
            status,
        )


def _snapshot(db) -> list[tuple]:
    return [
        tuple(r)
        for r in _q(
            db.admin,
            "SELECT event_id, tenant_id, status, created_at, published_at, payload::text "
            "FROM decision_outbox_events ORDER BY event_id",
        )
    ]


def _measure(dsn: str) -> dict:
    """``outbox_backlog`` exactly as ``/readyz`` runs it: DATABASE_URL and the service pool."""
    import persistence

    async def _run():
        try:
            return await persistence.outbox_backlog()
        finally:
            await persistence.close_pools()

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", dsn)
        return asyncio.run(_run())


def _role(dsn: str) -> dict:
    row = _q(
        dsn,
        "SELECT current_user AS role, rolsuper, rolbypassrls FROM pg_roles "
        "WHERE rolname = current_user",
    )[0]
    return dict(row)


def test_superuser_measures_the_pending_rows_of_every_tenant(outbox_db):
    _seed(outbox_db)
    before = _snapshot(outbox_db)
    assert _role(outbox_db.admin)["rolsuper"] is True
    state = _measure(outbox_db.admin)
    assert state["measured"] is True and state["reason"] is None
    assert state["pending_count"] == PENDING, "pending rows of both tenants, not the published one"
    age = state["oldest_pending_age_seconds"]
    assert OLDEST_SECONDS <= age < OLDEST_SECONDS + 600, age
    assert state["relay_implemented"] is False and state["delivery"] == "not_delivered"
    assert _snapshot(outbox_db) == before, "the probe must leave every row as it found it"


def test_empty_outbox_is_measured_zero_with_no_age(outbox_db):
    _empty(outbox_db)
    state = _measure(outbox_db.admin)
    measured = (state["measured"], state["pending_count"], state["oldest_pending_age_seconds"])
    assert measured == (True, 0, None)


def test_nobypassrls_role_is_unmeasured_not_a_false_zero(outbox_db):
    _seed(outbox_db)
    assert _role(outbox_db.app) == {
        "role": outbox_db.roles["app"],
        "rolsuper": False,
        "rolbypassrls": False,
    }
    # The false zero the probe refuses: this role's own unbound count reads 0 over 4 rows.
    own = _q(outbox_db.app, "SELECT count(*) AS n FROM decision_outbox_events")[0]["n"]
    total = _q(outbox_db.admin, "SELECT count(*) AS n FROM decision_outbox_events")[0]["n"]
    assert (own, total) == (0, PENDING + 1)

    state = _measure(outbox_db.app)
    assert state["measured"] is False
    assert state["reason"] == RLS_REASON
    assert state["pending_count"] is None and state["oldest_pending_age_seconds"] is None


def test_bypassrls_auditor_measures_every_tenant(outbox_db):
    _seed(outbox_db)
    assert _role(outbox_db.auditor) == {
        "role": outbox_db.roles["auditor"],
        "rolsuper": False,
        "rolbypassrls": True,
    }
    state = _measure(outbox_db.auditor)
    assert state["measured"] is True and state["reason"] is None
    assert state["pending_count"] == PENDING
    assert OLDEST_SECONDS <= state["oldest_pending_age_seconds"] < OLDEST_SECONDS + 600


def test_query_failure_is_unmeasured_and_carries_no_error_text(outbox_db):
    """A BYPASSRLS role without SELECT passes the role probe and fails on the aggregate."""
    _seed(outbox_db)
    state = _measure(outbox_db.noread)
    assert state["measured"] is False and state["reason"] == "query_failed"
    assert state["pending_count"] is None
    text = json.dumps(state).lower()
    assert "permission" not in text and "denied" not in text
    assert outbox_db.roles["noread"] not in text
