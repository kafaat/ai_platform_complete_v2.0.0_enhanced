"""Farm scope (v287, decision C) on a live PostgreSQL, with auth in a SEPARATE database.

Each case copies a template built from ``migrations/MANIFEST.txt`` without v287, seeds one
tenant (three farms' worth of rows plus a farm-less field, and a second tenant's farm), and
creates an auth database of its own whose ``users.id`` differ from the platform's for the same
people (platform 7..10, auth 42..45). Reads run under a throwaway NOSUPERUSER NOBYPASSRLS role.
Proven here:

* before v287 the platform, with ``SAHOOL_FARM_SCOPE_ENFORCE`` on, reads no grant and lists the
  tenant's farms as before (code ships before its migration);
* v287 applied while the platform runs is enforced on the next request, no restart (absence is
  not cached), with the grant read under the tenant context;
* after v287 with enforcement off (the GUC never set), every role sees exactly what it saw
  before, table by table;
* enforcement on with the backfilled grants (``farm_access_backfill.py`` reading identities
  through the auth DSN) reproduces the same visibility, and ``farm_access_diff.py`` exits 0;
* enforcement on without grants hides every farm row from non-owners (farm-less rows stay),
  the owner keeps everything, and the diff exits 1 with ``lost`` (negative control);
* a grant keyed by the platform users.id is not effective for the session (sub 42), while one
  keyed by the sub is: through RLS and through the real ``GET /api/v1/farms`` handler;
* a partial grant shows only that farm's rows and refuses a write on another farm;
* a narrow role with SELECT on fields only (the shape of sahool_ingest) still reads fields
  after v287: the policies never reference farm_access_grants while enforcement is off.
* a failed grant read (42501) fails the request (503) instead of falling back to the
  unhydrated user, which would show every farm; the pooled connection stays usable;
* the grant table alone (no sc_farm_visible) does not switch enforcement on;
* zero or revoked grants reach no farm; owner-wide access is tenant-bound;
* one pooled connection carries no farm, tenant, user or role GUC from one request to the next.

HTTP cases go through the real FastAPI app (httpx ASGI) with a platform-minted JWT.

The server is ``TEST_DATABASE_ADMIN_URL`` or ``TEST_DATABASE_URL`` (a superuser: it creates
databases and roles). ``FARM_SCOPE_CERTIFICATION_REQUIRED=1`` turns a missing database into a
failure; without it every case is a declared skip that says why.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# Switch read before any import: on a certifying runner a missing dependency must fail the
# module, not importorskip it into a green skip (certification-switch-before-importorskip).
_REQUIRED = os.getenv("FARM_SCOPE_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
    import fastapi  # noqa: F401
    import httpx
except ImportError:
    if _REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg")
    pytest.importorskip("fastapi")
    httpx = pytest.importorskip("httpx")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
OPS = ROOT / "scripts" / "ops"
DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
V287 = "v287_farm_access_grants.sql"
TABLES = ("farms", "fields", "seasons", "field_tasks", "farm_ledger_entries")
T1, T2 = str(uuid.uuid4()), str(uuid.uuid4())
GEOMETRY = json.dumps(
    {
        "type": "Polygon",
        "coordinates": [
            [[44.40, 15.55], [44.41, 15.55], [44.41, 15.56], [44.40, 15.56], [44.40, 15.55]]
        ],
    }
)
# (platform users.id, auth users.id = JWT sub, e-mail, role): different ids for the same person.
PEOPLE = [
    (7, 42, "manager@example.org", "manager"),
    (8, 43, "agro@example.org", "agronomist"),
    (9, 44, "worker@example.org", "worker"),
    (10, 45, "owner@example.org", "owner"),
]
SUBS = {role: str(sub) for _pid, sub, _email, role in PEOPLE}


def _manifest() -> list[str]:
    lines = (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8").splitlines()
    return [s for s in (line.strip() for line in lines) if s and not s.startswith("#")]


def _without_v287() -> list[str]:
    return [f for f in _manifest() if f != V287]


def _tail_from_v287() -> list[str]:
    files = _manifest()
    return files[files.index(V287) :]


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        if not await conn.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname = current_user"):
            return "the DSN role cannot create the throwaway databases and role (not superuser)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())


@pytest.fixture(autouse=True)
def _database_or_declared_skip():
    if _WHY:
        message = f"farm-scope live proof has no database: {_WHY}"
        if _REQUIRED:
            pytest.fail(message, pytrace=False)
        pytest.skip(f"declared skip (not a pass): {message}")


def _dsn(database: str) -> str:
    """``DSN`` with another database name (the scripts take DSNs, not connections)."""
    head, _, tail = DSN.rpartition("/")
    query = tail.partition("?")[2]
    return f"{head}/{database}" + (f"?{query}" if query else "")


def _dsn_as(database: str, user: str, password: str) -> str:
    """``DSN`` for ``database`` logged in as ``user`` (a throwaway LOGIN role)."""
    parts = urlsplit(_dsn(database))
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    return urlunsplit(parts._replace(netloc=f"{user}:{password}@{host}"))


async def _apply(conn, files: list[str]) -> None:
    for name in files:
        await conn.execute((ROOT / "migrations" / name).read_text(encoding="utf-8"))


async def _admin(sql: str) -> None:
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@pytest.fixture(scope="module")
def template():
    """A database holding the manifest without v287, copied per case."""
    if _WHY:
        yield None
        return
    name = f"fs_tpl_{uuid.uuid4().hex[:10]}"

    async def build():
        await _admin(f'CREATE DATABASE "{name}"')
        conn = await asyncpg.connect(_dsn(name))
        try:
            await _apply(conn, _without_v287())
            assert await conn.fetchval("SELECT to_regclass('public.farm_access_grants')") is None
        finally:
            await conn.close()

    asyncio.run(build())
    yield name
    asyncio.run(_admin(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


class Live:
    """One case: a platform database (from the template), an auth database, a NOBYPASSRLS role."""

    def __init__(self, template: str, people=None, platform_only=()):
        self.people = list(people or PEOPLE)
        self.platform_only = list(platform_only)  # (platform id, e-mail, role): no auth identity
        self.subs = {role: str(sub) for _pid, sub, _email, role in self.people}
        tag = uuid.uuid4().hex[:10]
        self.platform_db, self.auth_db, self.role = f"fs_p_{tag}", f"fs_a_{tag}", f"fs_app_{tag}"
        self.template = template

    async def __aenter__(self):
        await _admin(f'CREATE DATABASE "{self.platform_db}" TEMPLATE "{self.template}"')
        await _admin(f'CREATE DATABASE "{self.auth_db}"')
        await _admin(f'CREATE ROLE "{self.role}" NOLOGIN NOSUPERUSER NOBYPASSRLS')
        self.owner = await asyncpg.connect(_dsn(self.platform_db))
        await self.owner.execute(
            f'GRANT USAGE ON SCHEMA public TO "{self.role}";'
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{self.role}";'
        )
        await self._seed_platform()
        await self._seed_auth()

        async def setup(conn):
            await conn.execute(f'SET ROLE "{self.role}"')

        self.pool = await asyncpg.create_pool(
            _dsn(self.platform_db), min_size=1, max_size=2, setup=setup
        )
        return self

    async def __aexit__(self, *_exc):
        await self.pool.close()
        await self.owner.close()
        for db in (self.platform_db, self.auth_db):
            await _admin(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
        await _admin(f'DROP ROLE IF EXISTS "{self.role}"')
        return False

    async def _seed_platform(self):
        o = self.owner
        for farm, tenant in (("fs-farm-1", T1), ("fs-farm-2", T1), ("fs-farm-9", T2)):
            await o.execute(
                "INSERT INTO farms (farm_id, tenant_id, name) VALUES ($1, $2::uuid, $1)",
                farm,
                tenant,
            )
        fields = (("fs-field-1", "fs-farm-1", T1), ("fs-field-2", "fs-farm-2", T1),
                  ("fs-field-0", None, T1), ("fs-field-9", "fs-farm-9", T2))  # fmt: skip
        for field, farm, tenant in fields:
            await o.execute(
                "INSERT INTO fields (field_id, name, tenant_id, farm_id, geometry) "
                "VALUES ($1, $1, $2::uuid, $3, $4::jsonb)",
                field,
                tenant,
                farm,
                GEOMETRY,
            )
            await o.execute(
                "INSERT INTO seasons (season_id, tenant_id, field_id, crops, status) "
                "VALUES ($1, $2::uuid, $3, '[\"wheat\"]'::jsonb, 'active')",
                f"s-{field}",
                tenant,
                field,
            )
            await o.execute(
                "INSERT INTO field_tasks (field_id, tenant_id, task_type, status) "
                "VALUES ($1, $2::uuid, 'scouting', 'pending')",
                field,
                tenant,
            )
        ledger = (("e-1", "fs-farm-1", "fs-field-1", T1), ("e-1f", "fs-farm-1", None, T1),
                  ("e-2", "fs-farm-2", "fs-field-2", T1), ("e-0", None, "fs-field-0", T1),
                  ("e-00", None, None, T1), ("e-9", "fs-farm-9", "fs-field-9", T2))  # fmt: skip
        for entry, farm, field, tenant in ledger:
            await o.execute(
                "INSERT INTO farm_ledger_entries (entry_id, tenant_id, client_operation_id, "
                "request_digest, entry_type, direction, payment_method, category, amount, "
                "occurred_on, farm_id, field_id, created_by) VALUES ($1, $2::uuid, $1, "
                "repeat('a', 64), 'expense', 'outflow', 'cash', 'labour', 10, current_date, "
                "$3, $4, 'seed')",
                entry,
                tenant,
                farm,
                field,
            )
        for pid, _sub, email, role in self.people + [
            (i, None, e, r) for i, e, r in self.platform_only
        ]:
            await o.execute(
                "INSERT INTO users (id, email, password_hash, full_name, role, tenant_id, active) "
                "VALUES ($1, $2, 'x', $2, $3, $4::uuid, true)",
                pid,
                email,
                role,
                T1,
            )

    async def _seed_auth(self):
        """auth's own database: only what the scripts read, with auth's ids (42..45)."""
        conn = await asyncpg.connect(_dsn(self.auth_db))
        try:
            await conn.execute(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL, "
                "role VARCHAR(50), tenant_id UUID, active BOOLEAN DEFAULT TRUE)"
            )
            for _pid, sub, email, role in self.people:
                await conn.execute(
                    "INSERT INTO users (id, email, role, tenant_id) VALUES ($1, $2, $3, $4::uuid)",
                    sub,
                    email,
                    role,
                    T1,
                )
        finally:
            await conn.close()

    async def apply_v287(self):
        """The migrator's run from v287, then its broad re-grant to the application role
        (migrations/apply_in_compose.sh: GRANT ... ON ALL TABLES after the manifest)."""
        await _apply(self.owner, _tail_from_v287())
        await self.owner.execute(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{self.role}"'
        )

    async def grant(self, user_id: str, *farms: str):
        for farm in farms:
            await self.owner.execute(
                "INSERT INTO farm_access_grants (tenant_id, user_id, farm_id, granted_by) "
                "VALUES ($1::uuid, $2, $3, 'test')",
                T1,
                user_id,
                farm,
            )

    async def visible(self, role: str, *, enforce: bool) -> dict[str, list[str]]:
        """Row keys each table shows to ``role`` (sub as the session user) in tenant T1."""
        keys = {
            "farms": "farm_id",
            "fields": "field_id",
            "seasons": "season_id",
            "field_tasks": "field_id",
            "farm_ledger_entries": "entry_id",
        }
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true), "
                "set_config('app.current_user_id', $2, true), set_config('app.current_role', $3, true)",
                T1,
                self.subs[role],
                role,
            )
            if enforce:
                await conn.execute("SELECT set_config('app.enforce_farm_scope', 'on', true)")
            return {
                t: sorted(r[0] for r in await conn.fetch(f"SELECT {keys[t]} FROM {t}"))
                for t in TABLES
            }

    def platform_dsn(self) -> str:
        return _dsn(self.platform_db)

    def auth_dsn(self) -> str:
        return _dsn(self.auth_db)


def _ops(name: str):
    if str(OPS) not in sys.path:
        sys.path.insert(0, str(OPS))
    spec = importlib.util.spec_from_file_location(name, OPS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main
    from api import farm_scope
    from api.routers import farms

    return main, farm_scope, farms


def _user(role: str, *, sub: str | None = None, tenant: str = T1):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(
        user_id=sub or SUBS[role], tenant_id=tenant, role=UserRole(role), name_ar="مستخدم"
    )


async def _get_farms(user) -> tuple[int, object]:
    """``GET /api/v1/farms`` through the real FastAPI app (httpx ASGI), as ``user``'s JWT."""
    main, _farm_scope, _farms = _platform()
    token = main.create_token(user)
    transport = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://platform") as client:
        response = await client.get("/api/v1/farms", headers={"Authorization": f"Bearer {token}"})
    body = response.json()
    if response.status_code == 200:
        body = sorted(f["farm_id"] for f in body)
    return response.status_code, body


@pytest.fixture
def platform(monkeypatch):
    """The platform module with the flag ON, an empty presence cache and no rate limit."""
    main, farm_scope, _farms = _platform()
    monkeypatch.setenv(farm_scope.FLAG, "on")
    monkeypatch.setattr(farm_scope, "_present", False)
    monkeypatch.setattr(main, "_RATE_LIMIT_PER_MIN", 0, raising=False)
    return main, farm_scope


ROLES = ("manager", "agronomist", "worker", "owner")
ALL_T1 = {
    "farms": ["fs-farm-1", "fs-farm-2"],
    "fields": ["fs-field-0", "fs-field-1", "fs-field-2"],
    "seasons": ["s-fs-field-0", "s-fs-field-1", "s-fs-field-2"],
    "field_tasks": ["fs-field-0", "fs-field-1", "fs-field-2"],
    "farm_ledger_entries": ["e-0", "e-00", "e-1", "e-1f", "e-2"],
}
FARMLESS_ONLY = {
    "farms": [],
    "fields": ["fs-field-0"],
    "seasons": ["s-fs-field-0"],
    "field_tasks": ["fs-field-0"],
    "farm_ledger_entries": ["e-0", "e-00"],
}


def _run(template, body, **live_kwargs):
    async def go():
        async with Live(template, **live_kwargs) as live:
            await body(live)

    asyncio.run(go())


def test_before_v287_the_platform_reads_no_grant_even_with_the_flag_on(
    template, monkeypatch, platform
):
    main, farm_scope = platform

    async def body(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        assert await _get_farms(_user("worker")) == (200, ["fs-farm-1", "fs-farm-2"])
        assert farm_scope._present is False

    _run(template, body)


def test_v287_applied_while_the_platform_runs_is_picked_up_without_a_restart(
    template, monkeypatch, platform
):
    """Absence is asked again: the same process, flag on, lists every farm before v287 and
    enforces right after it is applied. The worker's grant is read under the tenant GUC (the
    grant table is tenant-isolated by RLS), so a read before the tenant context would return no
    grant and the last request would show no farm."""
    main, farm_scope = platform

    async def body(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        assert await _get_farms(_user("worker")) == (200, ["fs-farm-1", "fs-farm-2"])
        assert farm_scope._present is False
        await live.apply_v287()
        assert await _get_farms(_user("worker")) == (200, [])
        assert farm_scope._present is True
        await live.grant(SUBS["worker"], "fs-farm-1")
        assert await _get_farms(_user("worker")) == (200, ["fs-farm-1"])

    _run(template, body)


def test_enforcement_off_leaves_every_role_seeing_what_it_saw_before(template):
    async def body(live):
        before = {role: await live.visible(role, enforce=False) for role in ROLES}
        assert all(seen == ALL_T1 for seen in before.values()), before
        await live.apply_v287()
        after_empty = {role: await live.visible(role, enforce=False) for role in ROLES}
        await live.grant(SUBS["worker"], "fs-farm-1")  # grants change nothing while off
        after_granted = {role: await live.visible(role, enforce=False) for role in ROLES}
        assert before == after_empty == after_granted

    _run(template, body)


def test_enforcement_on_with_the_backfill_reproduces_visibility_and_the_diff_is_clean(
    template, monkeypatch
):
    backfill, diff = _ops("farm_access_backfill"), _ops("farm_access_diff")

    async def body(live):
        before = {role: await live.visible(role, enforce=False) for role in ROLES}
        await live.apply_v287()
        dry = await backfill.run(live.platform_dsn(), live.auth_dsn(), apply=False)
        assert dry["planned_inserts"] == 8 and dry["written"] == 0
        assert await live.owner.fetchval("SELECT count(*) FROM farm_access_grants") == 0
        done = await backfill.run(live.platform_dsn(), live.auth_dsn(), apply=True)
        assert done["written"] == 8
        rows = await live.owner.fetch("SELECT DISTINCT user_id FROM farm_access_grants")
        assert sorted(r[0] for r in rows) == ["42", "43", "44", "45"], "keyed by auth's sub"
        again = await backfill.run(live.platform_dsn(), live.auth_dsn(), apply=True)
        assert again["written"] == 0 and again["already_active"] == 8
        after = {role: await live.visible(role, enforce=True) for role in ROLES}
        assert after == before
        report = await diff.collect(live.platform_dsn(), live.auth_dsn())
        assert report["identities"]["resolved"] == 4
        return report

    _run(template, body)
    # The CLI on the same kind of database: exit 0 when clean.
    holder = {}

    async def cli(live):
        await live.apply_v287()
        await backfill.run(live.platform_dsn(), live.auth_dsn(), apply=True)
        holder["dsn"] = (live.platform_dsn(), live.auth_dsn())
        monkeypatch.setenv("DATABASE_URL", holder["dsn"][0])
        monkeypatch.setenv("AUTH_DATABASE_URL", holder["dsn"][1])
        holder["rc"] = await asyncio.to_thread(diff.main, [])

    _run(template, cli)
    assert holder["rc"] == 0


def test_enforcement_on_without_grants_hides_farm_rows_and_the_diff_fails(template, monkeypatch):
    diff = _ops("farm_access_diff")
    holder = {}

    async def body(live):
        await live.apply_v287()
        for role in ("manager", "agronomist", "worker"):
            assert await live.visible(role, enforce=True) == FARMLESS_ONLY, role
        assert await live.visible("owner", enforce=True) == ALL_T1
        monkeypatch.setenv("DATABASE_URL", live.platform_dsn())
        monkeypatch.setenv("AUTH_DATABASE_URL", live.auth_dsn())
        holder["rc"] = await asyncio.to_thread(diff.main, [])
        holder["report"] = await diff.collect(live.platform_dsn(), live.auth_dsn())

    _run(template, body)
    assert holder["rc"] == 1
    assert _ops("farm_access_common").failures(holder["report"]) == ["lost"]
    assert {r["sub"] for r in holder["report"]["lost"]} == {"42", "43", "44"}


def test_a_grant_keyed_by_the_platform_users_id_is_not_effective_the_sub_is(
    template, monkeypatch, platform
):
    """Hospital requirement 3: platform users.id 7 and auth sub 42 are the same manager."""
    main, _farm_scope = platform
    diff = _ops("farm_access_diff")

    async def body(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        await live.apply_v287()
        await live.grant("7", "fs-farm-1", "fs-farm-2")  # the platform users.id: wrong key
        assert await live.visible("manager", enforce=True) == FARMLESS_ONLY
        assert await _get_farms(_user("manager")) == (200, [])
        wrong = await diff.collect(live.platform_dsn(), live.auth_dsn())
        assert {g["user_id"] for g in wrong["orphan_grants"]} == {"7"}
        assert "42" in {r["sub"] for r in wrong["lost"]}

        await live.grant("42", "fs-farm-1", "fs-farm-2")  # the JWT sub: right key
        assert await live.visible("manager", enforce=True) == ALL_T1
        assert await _get_farms(_user("manager")) == (200, ["fs-farm-1", "fs-farm-2"])

    _run(template, body)


def test_a_partial_grant_shows_only_that_farm_and_refuses_a_write_on_another(template):
    async def body(live):
        await live.apply_v287()
        await live.grant(SUBS["worker"], "fs-farm-1")
        seen = await live.visible("worker", enforce=True)
        assert seen == {
            "farms": ["fs-farm-1"],
            "fields": ["fs-field-0", "fs-field-1"],
            "seasons": ["s-fs-field-0", "s-fs-field-1"],
            "field_tasks": ["fs-field-0", "fs-field-1"],
            "farm_ledger_entries": ["e-0", "e-00", "e-1", "e-1f"],
        }

        async def insert_field(farm: str) -> str:
            async with live.pool.acquire() as conn, conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true), "
                    "set_config('app.current_user_id', $2, true), "
                    "set_config('app.current_role', 'worker', true), "
                    "set_config('app.enforce_farm_scope', 'on', true)",
                    T1,
                    SUBS["worker"],
                )
                try:
                    await conn.execute(
                        "INSERT INTO fields (field_id, name, tenant_id, farm_id, geometry) "
                        "VALUES ($1, $1, $2::uuid, $3, $4::jsonb)",
                        f"w-{farm}",
                        T1,
                        farm,
                        GEOMETRY,
                    )
                except asyncpg.InsufficientPrivilegeError as exc:
                    return type(exc).__name__
                return "inserted"

        assert await insert_field("fs-farm-2") == "InsufficientPrivilegeError"
        assert await insert_field("fs-farm-1") == "inserted"

    _run(template, body)


def test_a_role_with_select_on_fields_only_still_reads_fields_after_v287(template):
    """sahool_ingest holds SELECT ON fields and nothing on farm_access_grants. A policy that
    referenced the grant table (even in a branch never taken) failed its reads with
    "permission denied for table farm_access_grants" while enforcement was off."""

    async def body(live):
        narrow = f"{live.role}_narrow"
        await live.owner.execute(
            f'CREATE ROLE "{narrow}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
            f'GRANT USAGE ON SCHEMA public TO "{narrow}"; GRANT SELECT ON fields TO "{narrow}";'
            # sahool_ingest's column grant on field_tasks (migrations/apply_in_compose.sh)
            "GRANT SELECT (tenant_id, field_id, source_scouting_pin_id, task_id, status) "
            f'ON field_tasks TO "{narrow}";'
        )
        try:
            await live.apply_v287()

            async def read(sql: str) -> int:
                async with live.owner.transaction():
                    await live.owner.execute(f'SET LOCAL ROLE "{narrow}"')
                    await live.owner.execute(
                        "SELECT set_config('app.current_tenant', $1, true)", T1
                    )
                    return len(await live.owner.fetch(sql))

            assert await read("SELECT 1 FROM fields") == 3
            assert await read("SELECT task_id, status FROM field_tasks") == 3
        finally:
            await live.owner.execute(f'DROP OWNED BY "{narrow}"; DROP ROLE "{narrow}"')

    _run(template, body)


# ── reviewer criteria: fail closed, partial schema, empty/revoked grants, pooling ──


def test_a_failed_grant_read_fails_the_request_instead_of_widening(template, monkeypatch, platform):
    """Flag on, v287 present, but the grant read is refused (42501). The manager has no grant,
    so the correct answer is no farm; a fallback to the unhydrated user would set no farm GUC
    and show every farm. The request must fail instead."""
    main, _farm_scope = platform

    async def body(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        await live.apply_v287()
        await live.owner.execute(f'REVOKE SELECT ON farm_access_grants FROM "{live.role}"')
        status, payload = await _get_farms(_user("manager"))
        assert status == 503, payload
        # The pooled connection is still usable afterwards (the failed transaction rolled back).
        await live.owner.execute(f'GRANT SELECT ON farm_access_grants TO "{live.role}"')
        assert await _get_farms(_user("manager")) == (200, [])

    _run(template, body)


def test_the_grant_table_alone_does_not_switch_enforcement_on(template, monkeypatch, platform):
    """Partial schema: farm_access_grants exists, sc_farm_visible() does not. Scope stays off
    (the probe needs both objects), the farm GUC is not set, and visibility is unchanged."""
    main, farm_scope = platform

    async def body(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        await live.owner.execute(
            "CREATE TABLE farm_access_grants (tenant_id UUID NOT NULL, user_id TEXT NOT NULL, "
            "farm_id VARCHAR(50) NOT NULL REFERENCES farms(farm_id), is_active BOOLEAN NOT NULL "
            "DEFAULT TRUE, granted_by TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT "
            "now(), PRIMARY KEY (tenant_id, user_id, farm_id));"
            f'GRANT SELECT ON farm_access_grants TO "{live.role}"'
        )
        assert await live.owner.fetchval("SELECT to_regprocedure('sc_farm_visible(text)')") is None
        assert await _get_farms(_user("worker")) == (200, ["fs-farm-1", "fs-farm-2"])
        user = _user("worker")
        async with main.tenant_connection(user) as conn:
            guc = await conn.fetchval("SELECT current_setting('app.enforce_farm_scope', true)")
        assert guc in (None, "") and user.farm_scope_loaded is False
        assert farm_scope._present is False

    _run(template, body)


def test_empty_and_revoked_grants_reach_no_farm_and_owner_access_is_tenant_bound(
    template, monkeypatch, platform
):
    main, _farm_scope = platform

    async def body(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        await live.apply_v287()
        assert await _get_farms(_user("worker")) == (200, []), "no grant: no farm"
        await live.grant(SUBS["worker"], "fs-farm-1", "fs-farm-2")
        assert await _get_farms(_user("worker")) == (200, ["fs-farm-1", "fs-farm-2"])
        await live.owner.execute(
            "UPDATE farm_access_grants SET is_active = false WHERE user_id = $1", SUBS["worker"]
        )
        assert await _get_farms(_user("worker")) == (200, []), "revoked grants: no farm"
        # Owner-wide access is explicit (role) and still tenant-bound: tenant 2's farm never.
        assert await _get_farms(_user("owner")) == (200, ["fs-farm-1", "fs-farm-2"])
        assert await _get_farms(_user("owner", sub="99", tenant=T2)) == (200, ["fs-farm-9"])

    _run(template, body)


def test_a_single_pooled_connection_leaks_no_farm_tenant_or_user_setting(
    template, monkeypatch, platform
):
    """set_config(..., true) is transaction-local: after request A (flag on, user 44 in T1)
    the same connection carries no farm, tenant or user GUC into request B."""
    main, farm_scope = platform

    async def body(live):
        await live.apply_v287()
        await live.grant(SUBS["worker"], "fs-farm-1")

        async def setup(conn):
            await conn.execute(f'SET ROLE "{live.role}"')

        pool = await asyncpg.create_pool(live.platform_dsn(), min_size=1, max_size=1, setup=setup)
        try:
            monkeypatch.setattr(main, "_DB_POOL", pool)
            assert await _get_farms(_user("worker")) == (200, ["fs-farm-1"])  # A: enforced
            async with pool.acquire() as conn:
                pid = await conn.fetchval("SELECT pg_backend_pid()")
                left = await conn.fetchrow(
                    "SELECT current_setting('app.enforce_farm_scope', true) AS farm, "
                    "current_setting('app.current_tenant', true) AS tenant, "
                    "current_setting('app.current_user_id', true) AS user_id, "
                    "current_setting('app.current_role', true) AS role"
                )
            assert all(v in (None, "") for v in left.values()), dict(left)
            # B, another tenant's manager without grants on the same connection: its own farm
            # is hidden (enforced for it too), and nothing of tenant 1 shows through.
            assert await _get_farms(_user("manager", sub="99", tenant=T2)) == (200, [])
            # C, flag off on the same connection: the worker sees its tenant as before v287.
            monkeypatch.delenv(farm_scope.FLAG)
            assert await _get_farms(_user("worker")) == (200, ["fs-farm-1", "fs-farm-2"])
            async with pool.acquire() as conn:
                assert await conn.fetchval("SELECT pg_backend_pid()") == pid, "one connection"
            assert pool.get_size() == 1
        finally:
            await pool.close()

    _run(template, body)


# ── review findings 1-4 and nit 5 ─────────────────────────────────────────────


async def _write_as(live, role: str, sql: str, *args, sub: str | None = None) -> str:
    """Run one write as ``role`` under enforcement; 'ok' or the refusal's class name."""
    async with live.pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true), "
            "set_config('app.current_user_id', $2, true), "
            "set_config('app.current_role', $3, true), "
            "set_config('app.enforce_farm_scope', 'on', true)",
            T1,
            sub or live.subs[role],
            role,
        )
        try:
            await conn.execute(sql, *args)
        except asyncpg.InsufficientPrivilegeError as exc:
            return type(exc).__name__
    return "ok"


_LEDGER_INSERT = (
    "INSERT INTO farm_ledger_entries (entry_id, tenant_id, client_operation_id, request_digest, "
    "entry_type, direction, payment_method, category, amount, occurred_on, farm_id, field_id, "
    "created_by) VALUES ($1, $2::uuid, $1, repeat('b', 64), 'expense', 'outflow', 'cash', "
    "'labour', 5, current_date, $3, $4, 'worker')"
)
_FIELD_INSERT = (
    "INSERT INTO fields (field_id, name, tenant_id, farm_id, geometry) "
    "VALUES ($1, $1, $2::uuid, $3, $4::jsonb)"
)


def test_a_non_owner_cannot_move_rows_out_of_farm_scope_through_a_null_farm(template):
    """Finding 1: a NULL farm is visible to the whole tenant, so under enforcement a non-owner
    may not write one: not by nulling a farm, not by inserting a farm-less field or ledger
    entry, and not by moving a season or task onto a farm-less field."""
    refused = "InsufficientPrivilegeError"

    async def body(live):
        await live.apply_v287()
        await live.grant(live.subs["worker"], "fs-farm-1")
        assert (
            await _write_as(
                live, "worker", "UPDATE fields SET farm_id = NULL WHERE field_id = $1", "fs-field-1"
            )
            == refused
        )
        assert (
            await _write_as(live, "worker", _FIELD_INSERT, "w-null", T1, None, GEOMETRY) == refused
        )
        assert (
            await _write_as(live, "worker", _LEDGER_INSERT, "w-e-null", T1, None, None) == refused
        )
        assert (
            await _write_as(live, "worker", _LEDGER_INSERT, "w-e-f0", T1, None, "fs-field-0")
            == refused
        )
        assert (
            await _write_as(
                live,
                "worker",
                "UPDATE field_tasks SET field_id = 'fs-field-0' WHERE field_id = $1",
                "fs-field-1",
            )
            == refused
        )
        assert (
            await _write_as(
                live,
                "worker",
                "INSERT INTO seasons (season_id, tenant_id, field_id, crops, status) "
                "VALUES ('w-s0', $1::uuid, 'fs-field-0', '[]'::jsonb, 'planned')",
                T1,
            )
            == refused
        )
        # Controls: a write inside the granted farm passes; the owner may still write NULL.
        assert (
            await _write_as(live, "worker", _FIELD_INSERT, "w-ok", T1, "fs-farm-1", GEOMETRY)
            == "ok"
        )
        assert await _write_as(live, "owner", _FIELD_INSERT, "o-null", T1, None, GEOMETRY) == "ok"
        # Nothing of farm 1 leaked to a zero-grant user.
        seen = await live.visible("manager", enforce=True)
        assert seen["fields"] == ["fs-field-0", "o-null"] and seen["farms"] == []

    _run(template, body)


C_PEOPLE = [(1, 2, "manager@example.org", "manager"), (2, 1, "worker@example.org", "worker")]


def test_colliding_ids_a_platform_id_keyed_grant_reaches_the_wrong_person_and_the_diff_fails(
    template, monkeypatch, platform
):
    """Finding 2 / hospital condition 3 under collision: platform ids 1,2 and auth subs 2,1
    for the same two people (both users.id columns are SERIAL from 1)."""
    main, _farm_scope = platform
    diff, backfill = _ops("farm_access_diff"), _ops("farm_access_backfill")
    common = _ops("farm_access_common")
    holder = {}

    async def body(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        await live.apply_v287()
        manager, worker = _user("manager", sub="2"), _user("worker", sub="1")
        # The backfill keys by auth's sub: clean, and enforcement shows each person both farms.
        assert (await backfill.run(live.platform_dsn(), live.auth_dsn(), apply=True))[
            "written"
        ] == 4
        assert common.failures(await diff.collect(live.platform_dsn(), live.auth_dsn())) == []
        assert await _get_farms(worker) == (200, ["fs-farm-1", "fs-farm-2"])
        await live.owner.execute("DELETE FROM farm_access_grants")
        # An admin keys the worker's grant by the worker's PLATFORM id (2) = the manager's sub.
        await live.owner.execute(
            "INSERT INTO farm_access_grants (tenant_id, user_id, farm_id, granted_by) "
            "VALUES ($1::uuid, '2', 'fs-farm-1', 'admin:by-platform-id')",
            T1,
        )
        assert await _get_farms(worker) == (200, []), "not effective for the intended person"
        assert await _get_farms(manager) == (200, ["fs-farm-1"]), "it reaches the other person"
        holder["wrong"] = await diff.collect(live.platform_dsn(), live.auth_dsn())
        await live.owner.execute(
            "UPDATE farm_access_grants SET user_id = '1', granted_by = 'admin:by-sub'"
        )
        assert await _get_farms(worker) == (200, ["fs-farm-1"]), "keyed by the sub: effective"

    _run(template, body, people=C_PEOPLE)
    assert "platform_id_keyed_grants" in common.failures(holder["wrong"])


def test_the_regional_bulletin_filter_keeps_farm_less_fields_on_postgresql(template):
    """Finding 3 on the real SQL: a restricted scope still returns the farm-less field."""
    _main, _farm_scope, _farms = _platform()
    from api.routers.regional_bulletin import _BULLETIN_SQL

    async def body(live):
        rows = await live.owner.fetch(_BULLETIN_SQL, ["fs-farm-1"])
        assert sorted(
            r["field_id"] for r in rows if r["tenant_id"] is not None and str(r["tenant_id"]) == T1
        ) == [
            "fs-field-0",
            "fs-field-1",
        ]

    _run(template, body)


def test_the_backfill_refuses_to_write_on_an_unresolved_identity(template, monkeypatch):
    """Finding 4: a platform user with no auth identity stops the backfill, dry run and
    --apply alike, and --apply writes nothing."""
    backfill = _ops("farm_access_backfill")
    holder = {}

    async def body(live):
        await live.apply_v287()
        monkeypatch.setenv("DATABASE_URL", live.platform_dsn())
        monkeypatch.setenv("AUTH_DATABASE_URL", live.auth_dsn())
        holder["dry"] = await asyncio.to_thread(backfill.main, [])
        holder["apply"] = await asyncio.to_thread(backfill.main, ["--apply"])
        holder["written"] = await live.owner.fetchval("SELECT count(*) FROM farm_access_grants")

    _run(template, body, platform_only=[(11, "stray@example.org", "worker")])
    assert (holder["dry"], holder["apply"], holder["written"]) == (1, 1, 0)


class _NoResetConnection(asyncpg.Connection):
    """A real connection whose pool release skips RESET ALL, so a session-level set_config
    (is_local false) would survive into the next request instead of being wiped by asyncpg."""

    def get_reset_query(self):
        return ""


def test_no_guc_survives_the_transaction_even_without_the_pool_reset(
    template, monkeypatch, platform
):
    """Nit 5: asyncpg's RESET ALL hid is_local=false; without it, only transaction-local
    settings leave nothing behind."""
    main, _farm_scope = platform

    async def body(live):
        await live.apply_v287()
        await live.grant(live.subs["worker"], "fs-farm-1")

        async def setup(conn):
            await conn.execute(f'SET ROLE "{live.role}"')

        pool = await asyncpg.create_pool(
            live.platform_dsn(),
            min_size=1,
            max_size=1,
            setup=setup,
            connection_class=_NoResetConnection,
        )
        try:
            monkeypatch.setattr(main, "_DB_POOL", pool)
            assert await _get_farms(_user("worker")) == (200, ["fs-farm-1"])
            async with pool.acquire() as conn:
                left = await conn.fetchrow(
                    "SELECT current_setting('app.enforce_farm_scope', true) AS farm, "
                    "current_setting('app.current_tenant', true) AS tenant, "
                    "current_setting('app.current_user_id', true) AS user_id, "
                    "current_setting('app.current_role', true) AS role"
                )
            assert all(v in (None, "") for v in left.values()), dict(left)
        finally:
            await pool.close()

    _run(template, body)


# ── delta review A: only the operator writes grants; B: no DELETE of what cannot be written ──


def _migrator_revoke(role_var: str) -> str:
    """The REVOKE migrations/apply_in_compose.sh runs on farm_access_grants for ``role_var``."""
    text = (ROOT / "migrations" / "apply_in_compose.sh").read_text(encoding="utf-8")
    m = re.search(
        r"SELECT format\('(REVOKE [A-Z, ]+ ON TABLE public\.farm_access_grants FROM %I)', "
        r":'" + role_var + r"'\)",
        text,
    )
    assert m, f"apply_in_compose.sh revokes no write on farm_access_grants from :{role_var}"
    return m.group(1)


async def _as_role(live, role: str, sql: str, *args, owner_guc: bool = True) -> str:
    async with live.owner.transaction():
        await live.owner.execute(f'SET LOCAL ROLE "{role}"')
        if owner_guc:
            await live.owner.execute(
                "SELECT set_config('app.current_tenant', $1, true), "
                "set_config('app.current_user_id', '45', true), "
                "set_config('app.current_role', 'owner', true)",
                T1,
            )
        try:
            status = await live.owner.execute(sql, *args)
        except asyncpg.PostgresError as exc:
            return exc.sqlstate
    return status


def test_only_the_operator_writes_grants_and_the_backfill_label_cannot_be_forged(template):
    """A: the application role (NOBYPASSRLS, owner GUC set as for any owner JWT) and the jobs
    role (BYPASSRLS) may not write farm_access_grants; a role that somehow may write cannot use
    the backfill's provenance label; the migration owner's backfill still writes."""
    backfill = _ops("farm_access_backfill")
    holder = {}

    async def body(live):
        jobs, writer, op = f"{live.role}_jobs", f"{live.role}_w", f"{live.role}_op"
        await live.apply_v287()  # includes the migrator's broad re-grant to the app role
        await live.owner.execute(_migrator_revoke("app_role").replace("%I", f'"{live.role}"'))
        await live.owner.execute(
            f'CREATE ROLE "{jobs}" NOLOGIN NOSUPERUSER BYPASSRLS;'
            f'GRANT USAGE ON SCHEMA public TO "{jobs}";'
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{jobs}";'
            + _migrator_revoke("jobs_role").replace("%I", f'"{jobs}"')
        )
        await live.grant("42", "fs-farm-1")
        try:
            insert = (
                "INSERT INTO farm_access_grants (tenant_id, user_id, farm_id, granted_by) "
                "VALUES ($1::uuid, '7', 'fs-farm-2', 'backfill:decision-C')"
            )
            for role in (live.role, jobs):
                assert await _as_role(live, role, insert, T1) == "42501", role
                assert (
                    await _as_role(live, role, "UPDATE farm_access_grants SET is_active = false")
                    == "42501"
                ), role
                assert await _as_role(live, role, "DELETE FROM farm_access_grants") == "42501", role

            # v287 itself narrows a role that holds write on the table (no apply_in_compose run).
            await live.owner.execute(
                f'CREATE ROLE "{writer}" NOLOGIN NOSUPERUSER BYPASSRLS;'
                f'GRANT USAGE ON SCHEMA public TO "{writer}";'
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON farm_access_grants TO "{writer}"'
            )
            # The trigger: a non-operator that can write may not claim the backfill's label.
            assert await _as_role(live, writer, insert, T1) == "42501"
            ok = insert.replace("'backfill:decision-C'", "'admin:by-hand'")
            assert await _as_role(live, writer, ok, T1) == "INSERT 0 1"
            await _apply(live.owner, ["v287_farm_access_grants.sql"])
            assert not await live.owner.fetchval(
                "SELECT has_table_privilege($1, 'public.farm_access_grants', 'INSERT')", writer
            ), "re-applying v287 revokes write from a non-owner role"

            # The backfill as a BYPASSRLS non-superuser: dry run reads, --apply refuses (exit 2).
            await live.owner.execute(
                f"CREATE ROLE \"{op}\" LOGIN PASSWORD 'op-pw' NOSUPERUSER BYPASSRLS;"
                f'GRANT USAGE ON SCHEMA public TO "{op}";'
                f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{op}"'
            )
            op_dsn = _dsn_as(live.platform_db, op, "op-pw")
            dry = await backfill.run(op_dsn, live.auth_dsn(), apply=False)
            assert dry["written"] == 0 and dry["planned_inserts"] > 0
            with pytest.raises(backfill.fac.Precondition):
                await backfill.run(op_dsn, live.auth_dsn(), apply=True)
            # The migration owner (the operator) still writes.
            await live.owner.execute("DELETE FROM farm_access_grants")
            holder["written"] = (
                await backfill.run(live.platform_dsn(), live.auth_dsn(), apply=True)
            )["written"]
        finally:
            for r in (jobs, writer, op):
                await live.owner.execute(
                    f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{r}') "
                    f"THEN EXECUTE 'DROP OWNED BY \"{r}\"'; EXECUTE 'DROP ROLE \"{r}\"'; "
                    "END IF; END $$"
                )

    _run(template, body)
    assert holder["written"] == 8


async def _delete_as(live, role: str, sql: str, *args) -> str:
    async with live.pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true), "
            "set_config('app.current_user_id', $2, true), "
            "set_config('app.current_role', $3, true), "
            "set_config('app.enforce_farm_scope', 'on', true)",
            T1,
            live.subs[role],
            role,
        )
        try:
            return await conn.execute(sql, *args)
        except asyncpg.PostgresError as exc:
            return exc.sqlstate


def test_a_non_owner_cannot_delete_what_it_cannot_write(template):
    """B: farm-less rows are read-only for non-owners under enforcement, DELETE included; a
    delete inside a granted farm passes; the owner may delete farm-less rows."""

    async def body(live):
        await live.apply_v287()
        await live.grant(live.subs["worker"], "fs-farm-1")
        for sql, key in (
            ("DELETE FROM seasons WHERE season_id = $1", "s-fs-field-0"),
            ("DELETE FROM field_tasks WHERE field_id = $1", "fs-field-0"),
            ("DELETE FROM fields WHERE field_id = $1", "fs-field-0"),
            ("DELETE FROM farm_ledger_entries WHERE entry_id = $1", "e-00"),
        ):
            assert await _delete_as(live, "worker", sql, key) == "DELETE 0", sql
        seen = await live.visible("manager", enforce=False)
        assert "fs-field-0" in seen["fields"] and "s-fs-field-0" in seen["seasons"]
        assert "fs-field-0" in seen["field_tasks"] and "e-00" in seen["farm_ledger_entries"]
        assert (
            await _delete_as(live, "worker", "DELETE FROM seasons WHERE season_id = 's-fs-field-1'")
            == "DELETE 1"
        )
        assert (
            await _delete_as(live, "owner", "DELETE FROM seasons WHERE season_id = 's-fs-field-0'")
            == "DELETE 1"
        )

    _run(template, body)
