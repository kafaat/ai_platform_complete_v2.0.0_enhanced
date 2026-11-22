"""Farm scope in the platform (Service Center SC-1, decision C), without a database.

``api.farm_scope.load_farm_scope`` must change nothing unless BOTH the operator flag
``SAHOOL_FARM_SCOPE_ENFORCE`` is on AND migration v287 is applied; ``tenant_connection`` sets
``app.enforce_farm_scope`` only when it returns True. ``core.authorization.farm_restriction``
reads a hydrated scope exactly (empty = no farm) and keeps the legacy contract otherwise
(empty = every farm). What PostgreSQL does with the policies is proven on a live database in
``test_farm_access_scope_live_pg.py``.
"""

from __future__ import annotations

import ast
import asyncio
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
if str(PLATFORM) not in sys.path:
    sys.path.insert(0, str(PLATFORM))

from api import farm_scope  # noqa: E402
from core.authorization import (  # noqa: E402
    Permission,
    audit_user_permissions,
    authorize,
    farm_restriction,
    farms_accessible_to_user,
)
from core.canonical_schemas import UserRole, UserSchema  # noqa: E402

pytestmark = pytest.mark.unit

TENANT = "00000000-0000-0000-0000-0000000000a1"
MAIN = PLATFORM / "api" / "main.py"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(farm_scope, "_present", False)
    monkeypatch.delenv(farm_scope.FLAG, raising=False)


class _Catalog:
    """A connection that records every statement; v287 present or not, grants as given."""

    def __init__(self, present: bool, grants: list[str] | None = None):
        self.present, self.grants, self.log = present, grants or [], []

    async def fetchval(self, sql, *args):
        self.log.append(("fetchval", sql))
        assert "to_regclass('public.farm_access_grants')" in sql
        return self.present

    async def fetch(self, sql, *args):
        self.log.append(("fetch", sql, args))
        assert self.present, "grants must never be read before v287 exists"
        return [{"farm_id": f} for f in self.grants]

    async def execute(self, sql, *args):
        self.log.append(("execute", sql, args))
        return "SELECT 1"

    def transaction(self):
        return _Null()


class _Null:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *_a):
        return False


def _user(role=UserRole.MANAGER, sub="42") -> UserSchema:
    return UserSchema(sub, TENANT, role, "مستخدم")


# ── load_farm_scope: two switches ─────────────────────────────────────────────


async def test_flag_off_touches_nothing_even_with_v287_applied():
    user = _user()
    # An opaque object: any query on it raises AttributeError.
    assert await farm_scope.load_farm_scope(object(), user) is False
    assert (user.farm_scope_loaded, user.farm_ids_access) == (False, [])


@pytest.mark.parametrize("value", ["", "0", "off", "false", "no", "enabled"])
async def test_only_explicit_on_values_switch_it_on(monkeypatch, value):
    monkeypatch.setenv(farm_scope.FLAG, value)
    assert farm_scope.enforcement_requested() is False


async def test_flag_on_before_v287_reads_no_grant_and_asks_the_catalog_again(monkeypatch):
    monkeypatch.setenv(farm_scope.FLAG, "on")
    conn, user = _Catalog(present=False), _user()
    assert await farm_scope.load_farm_scope(conn, user) is False
    assert await farm_scope.load_farm_scope(conn, user) is False
    assert [entry[0] for entry in conn.log] == ["fetchval", "fetchval"], "absence is not cached"
    assert user.farm_scope_loaded is False


async def test_flag_on_after_v287_hydrates_from_grants_keyed_by_the_jwt_sub(monkeypatch):
    monkeypatch.setenv(farm_scope.FLAG, "1")
    conn = _Catalog(present=True, grants=["farm-a"])
    worker = _user(UserRole.WORKER, sub="42")
    assert await farm_scope.load_farm_scope(conn, worker) is True
    assert (worker.farm_scope_loaded, worker.farm_access_all, worker.farm_ids_access) == (
        True,
        False,
        ["farm-a"],
    )
    _, sql, args = conn.log[-1]
    assert args == (TENANT, "42"), "the grant key is user.user_id, i.e. the JWT sub"
    owner = _user(UserRole.OWNER, sub="1")
    assert await farm_scope.load_farm_scope(conn, owner) is True
    assert owner.farm_access_all is True
    assert [e[0] for e in conn.log].count("fetchval") == 1, "presence is cached"


def test_the_probe_reads_the_catalog_for_both_v287_objects():
    assert "to_regprocedure('public.sc_farm_visible(text)') IS NOT NULL" in farm_scope._PROBE
    assert "to_regclass('public.farm_access_grants') IS NOT NULL" in farm_scope._PROBE
    assert "information_schema" not in farm_scope._PROBE


# ── tenant_connection, executed from main.py's own source ─────────────────────


def _tenant_connection(conn):
    fn = next(
        n
        for n in ast.parse(MAIN.read_text(encoding="utf-8")).body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "tenant_connection"
    )

    class _Acquire:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, *_a):
            return False

    class _Pool:
        def acquire(self):
            return _Acquire()

    namespace = {
        "asynccontextmanager": asynccontextmanager,
        "get_pool": lambda: _Pool(),
        "load_farm_scope": farm_scope.load_farm_scope,
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(MAIN), "exec"), namespace)  # noqa: S102
    return namespace["tenant_connection"]


def _statements(conn, user) -> list[str]:
    async def run():
        async with _tenant_connection(conn)(user):
            pass

    asyncio.run(run())
    return [e[1] for e in conn.log if e[0] == "execute"]


def _enforce_set(statements: list[str]) -> bool:
    return any("app.enforce_farm_scope" in s for s in statements)


def test_tenant_connection_never_sets_the_farm_guc_while_the_flag_is_off():
    statements = _statements(_Catalog(present=True, grants=["farm-a"]), _user())
    assert len(statements) == 1 and "app.current_tenant" in statements[0]
    assert not _enforce_set(statements)


def test_tenant_connection_does_not_set_it_before_v287_even_when_the_flag_is_on(monkeypatch):
    monkeypatch.setenv(farm_scope.FLAG, "on")
    assert not _enforce_set(_statements(_Catalog(present=False), _user()))


def test_tenant_connection_sets_it_after_the_tenant_gucs_once_both_switches_hold(monkeypatch):
    monkeypatch.setenv(farm_scope.FLAG, "on")
    conn = _Catalog(present=True, grants=["farm-a"])
    statements = _statements(conn, _user())
    assert "app.current_tenant" in statements[0]
    assert statements[-1] == "SELECT set_config('app.enforce_farm_scope', 'on', true)"
    order = [e[0] if e[0] != "execute" else e[1] for e in conn.log]
    assert order.index("fetch") < order.index(statements[-1]), "grants first, then the GUC"
    assert order.index(statements[0]) < order.index("fetch"), "tenant GUCs before the grants"


# ── authorization: hydrated scope is exact, legacy scope unchanged ────────────


class _Farm:
    def __init__(self, farm_id, tenant_id=TENANT):
        self.farm_id, self.tenant_id = farm_id, tenant_id


def _hydrated(role, grants, all_farms=False) -> UserSchema:
    user = _user(role)
    user.farm_scope_loaded, user.farm_access_all, user.farm_ids_access = True, all_farms, grants
    return user


def test_legacy_unhydrated_user_keeps_every_farm_of_its_tenant():
    user = _user(UserRole.WORKER)
    assert farm_restriction(user) is None
    assert authorize(user, Permission.FIELD_VIEW, farm_id="farm-z").allowed
    assert audit_user_permissions(user)["farm_access"] == "all_in_tenant"


@pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.AGRONOMIST, UserRole.WORKER])
def test_hydrated_non_owner_without_grants_reaches_no_farm(role):
    user = _hydrated(role, [])
    assert farm_restriction(user) == frozenset()
    assert not authorize(user, Permission.FIELD_VIEW, farm_id="farm-a").allowed
    assert farms_accessible_to_user(user, [_Farm("farm-a")]) == []
    assert audit_user_permissions(user)["farm_access"] == []


def test_hydrated_grants_are_exact():
    user = _hydrated(UserRole.WORKER, ["farm-a"])
    assert authorize(user, Permission.FIELD_VIEW, farm_id="farm-a").allowed
    assert not authorize(user, Permission.FIELD_VIEW, farm_id="farm-b").allowed
    farms = [_Farm("farm-a"), _Farm("farm-b"), _Farm("farm-a", "other-tenant")]
    assert [f.farm_id for f in farms_accessible_to_user(user, farms)] == ["farm-a"]


def test_hydrated_owner_keeps_every_farm_even_with_some_individual_grants():
    owner = _hydrated(UserRole.OWNER, ["farm-a"], all_farms=True)
    assert farm_restriction(owner) is None
    assert authorize(owner, Permission.FARM_EDIT, farm_id="farm-b").allowed
    assert audit_user_permissions(owner)["farm_access"] == "all_in_tenant"


# ── failure never widens access; no error-catching; no DDL from a request ─────


class _GrantReadFails(_Catalog):
    """v287 is present, but the grant read fails (a privilege error, a dropped connection...)."""

    def __init__(self, exc: Exception):
        super().__init__(present=True)
        self.exc = exc

    async def fetch(self, sql, *args):
        self.log.append(("fetch", sql, args))
        raise self.exc


class _InsufficientPrivilege(Exception):
    sqlstate = "42501"


@pytest.mark.parametrize(
    "exc",
    [_InsufficientPrivilege("permission denied for table farm_access_grants"), ConnectionError()],
)
def test_a_failed_grant_read_fails_the_request_and_never_falls_back_to_all_farms(monkeypatch, exc):
    """Unhydrated + empty farm_ids_access means every farm (legacy contract), so a fallback
    after a failed read would widen access. The error must escape tenant_connection: the
    request body never runs, and the user is not left looking unrestricted-but-loaded."""
    monkeypatch.setenv(farm_scope.FLAG, "on")
    conn, user, entered = _GrantReadFails(exc), _user(UserRole.WORKER), []

    async def run():
        async with _tenant_connection(conn)(user):
            entered.append(True)

    with pytest.raises(type(exc)):
        asyncio.run(run())
    assert entered == [], "the request body must not run on a failed grant read"
    assert user.farm_scope_loaded is False and user.farm_ids_access == []
    assert not _enforce_set([e[1] for e in conn.log if e[0] == "execute"])


def _source_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def test_farm_scope_detects_schema_by_catalog_probe_and_catches_nothing():
    """A caught 42P01 would abort the RLS transaction; presence is asked of the catalog."""
    tree = _source_tree(PLATFORM / "api" / "farm_scope.py")
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Try)], "no try/except at all"
    text = (PLATFORM / "api" / "farm_scope.py").read_text(encoding="utf-8")
    assert "UndefinedTable" not in text and "42P01" not in text


_DDL = re.compile(r"\b(CREATE|ALTER|DROP|GRANT|REVOKE|TRUNCATE)\b", re.IGNORECASE)


def _sql_constants(node: ast.AST) -> list[str]:
    return [
        n.value
        for n in ast.walk(node)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and re.search(r"\b(SELECT|INSERT)\b", n.value)
    ]


def test_no_request_path_runs_ddl_or_grants_to_get_around_missing_schema():
    """Neither tenant_connection nor api.farm_scope issues DDL, a GRANT or an RLS change, and the
    only grant writer (insert_tenant_grants, for the operator backfill) is called by no route."""
    farm_scope_tree = _source_tree(PLATFORM / "api" / "farm_scope.py")
    tenant_connection = next(
        n
        for n in _source_tree(MAIN).body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "tenant_connection"
    )
    for sql in _sql_constants(farm_scope_tree) + _sql_constants(tenant_connection):
        assert not _DDL.search(sql), sql
    callers = [
        p
        for p in (PLATFORM / "api").rglob("*.py")
        if p.name != "farm_scope.py" and "insert_tenant_grants" in p.read_text(encoding="utf-8")
    ]
    assert callers == []
