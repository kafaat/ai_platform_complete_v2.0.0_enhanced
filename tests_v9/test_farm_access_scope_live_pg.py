"""Farm scope (v287, decision C) on a live PostgreSQL, with auth in a SEPARATE database.

Each case copies a template built from ``migrations/MANIFEST.txt`` without v287, seeds one
tenant (three farms' worth of rows plus a farm-less field, and a second tenant's farm), and
creates an auth database of its own whose ``users.id`` differ from the platform's for the same
people (platform 7..10, auth 42..45). Reads run under a throwaway NOSUPERUSER NOBYPASSRLS role.
Proven here:

* before v287 the platform, with ``SAHOOL_FARM_SCOPE_ENFORCE`` on, reads no grant and lists the
  tenant's farms as before (code ships before its migration);
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

The server is ``TEST_DATABASE_ADMIN_URL`` or ``TEST_DATABASE_URL`` (a superuser: it creates
databases and roles). ``FARM_SCOPE_CERTIFICATION_REQUIRED=1`` turns a missing database into a
failure; without it every case is a declared skip that says why.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# Switch read before any import: on a certifying runner a missing dependency must fail the
# module, not importorskip it into a green skip (certification-switch-before-importorskip).
_REQUIRED = os.getenv("FARM_SCOPE_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
    import fastapi  # noqa: F401
except ImportError:
    if _REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg")
    pytest.importorskip("fastapi")

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

    def __init__(self, template: str):
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
        for pid, _sub, email, role in PEOPLE:
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
            for _pid, sub, email, role in PEOPLE:
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
                SUBS[role],
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


def _user(role: str):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(user_id=SUBS[role], tenant_id=T1, role=UserRole(role), name_ar="مستخدم")


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


def _run(template, body):
    async def go():
        async with Live(template) as live:
            await body(live)

    asyncio.run(go())


def test_before_v287_the_platform_reads_no_grant_even_with_the_flag_on(template, monkeypatch):
    main, farm_scope, farms = _platform()
    monkeypatch.setenv(farm_scope.FLAG, "on")
    monkeypatch.setattr(farm_scope, "_present", False)

    async def body(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        user = _user("worker")
        listed = await farms.list_farms(user=user)
        assert sorted(f["farm_id"] for f in listed) == ["fs-farm-1", "fs-farm-2"]
        assert user.farm_scope_loaded is False and farm_scope._present is False

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


def test_a_grant_keyed_by_the_platform_users_id_is_not_effective_the_sub_is(template, monkeypatch):
    """Hospital requirement 3: platform users.id 7 and auth sub 42 are the same manager."""
    main, farm_scope, farms = _platform()
    monkeypatch.setenv(farm_scope.FLAG, "on")
    monkeypatch.setattr(farm_scope, "_present", False)
    diff = _ops("farm_access_diff")

    async def body(live):
        monkeypatch.setattr(main, "_DB_POOL", live.pool)
        await live.apply_v287()
        await live.grant("7", "fs-farm-1", "fs-farm-2")  # the platform users.id: wrong key
        assert await live.visible("manager", enforce=True) == FARMLESS_ONLY
        assert await farms.list_farms(user=_user("manager")) == []
        wrong = await diff.collect(live.platform_dsn(), live.auth_dsn())
        assert {g["user_id"] for g in wrong["orphan_grants"]} == {"7"}
        assert "42" in {r["sub"] for r in wrong["lost"]}

        await live.grant("42", "fs-farm-1", "fs-farm-2")  # the JWT sub: right key
        assert await live.visible("manager", enforce=True) == ALL_T1
        user = _user("manager")
        listed = await farms.list_farms(user=user)
        assert sorted(f["farm_id"] for f in listed) == ["fs-farm-1", "fs-farm-2"]
        assert user.farm_scope_loaded and user.farm_ids_access == ["fs-farm-1", "fs-farm-2"]

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
