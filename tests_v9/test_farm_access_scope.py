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
import re
import sys
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


def test_the_probe_reads_the_catalog_for_both_v287_objects():
    assert "to_regprocedure('public.sc_farm_visible(text)') IS NOT NULL" in farm_scope._PROBE
    assert "to_regclass('public.farm_access_grants') IS NOT NULL" in farm_scope._PROBE
    assert "information_schema" not in farm_scope._PROBE


# ── tenant_connection and load_farm_scope: the order, read from the source ────
#
# No stand-in connection (FAKE-CONNECTION-ENFORCES-NOTHING-01): what PostgreSQL does with this
# order (RLS on the grant read, the enforcement GUC, a refused read failing the request) is
# proven in test_farm_access_scope_live_pg.py. These checks pin the order itself.


def _function(path: Path, name: str) -> ast.AsyncFunctionDef:
    return next(
        n
        for n in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == name
    )


def _body(fn: ast.AsyncFunctionDef) -> list[ast.stmt]:
    """The function body without its docstring."""
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        return body[1:]
    return body


def _awaited_call(node: ast.AST) -> ast.Call | None:
    if isinstance(node, ast.Expr):
        node = node.value
    if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
        return node.value
    return None


def _is_returns_false(stmts: list[ast.stmt]) -> bool:
    last = stmts[-1]
    return (
        isinstance(last, ast.Return)
        and isinstance(last.value, ast.Constant)
        and last.value.value is False
    )


def _transaction_body() -> list[ast.stmt]:
    fn = _function(MAIN, "tenant_connection")
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Try)], (
        "tenant_connection catches nothing: a failed grant read must escape before the yield"
    )
    acquire = next(s for s in _body(fn) if isinstance(s, ast.AsyncWith))
    (transaction,) = [s for s in acquire.body if isinstance(s, ast.AsyncWith)]
    assert ast.unparse(transaction.items[0].context_expr) == "conn.transaction()"
    return transaction.body


def test_tenant_connection_sets_the_farm_guc_only_when_load_farm_scope_says_so():
    """Tenant GUCs, then load_farm_scope (which reads the grants under them), then the farm GUC
    only on True, then the yield. Nothing else runs inside the transaction."""
    tenant_gucs, gate, handout = _transaction_body()
    call = _awaited_call(tenant_gucs)
    assert call is not None and ast.unparse(call.func) == "conn.execute"
    assert "set_config('app.current_tenant'" in call.args[0].value

    assert isinstance(gate, ast.If) and not gate.orelse
    assert ast.unparse(gate.test) == "await load_farm_scope(conn, user)"
    (set_farm,) = gate.body
    farm_call = _awaited_call(set_farm)
    assert farm_call is not None and ast.unparse(farm_call.func) == "conn.execute"
    assert [ast.unparse(a) for a in farm_call.args] == [
        "\"SELECT set_config('app.enforce_farm_scope', 'on', true)\""
    ]

    assert isinstance(handout, ast.Expr) and isinstance(handout.value, ast.Yield)
    assert ast.unparse(handout.value) == "(yield conn)"


def test_the_farm_guc_is_set_nowhere_else_on_the_request_path():
    sources = [MAIN, PLATFORM / "api" / "farm_scope.py"]
    hits = [
        (p.name, n.lineno)
        for p in sources
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and "set_config('app.enforce_farm_scope'" in n.value
    ]
    assert len(hits) == 1 and hits[0][0] == "main.py", hits


def test_load_farm_scope_queries_nothing_before_both_switches_hold():
    """The flag first (no query at all while it is off), then the catalog probe, and only then
    the grant read; both refusals return False before the user is touched."""
    flag, probe, *rest = _body(_function(PLATFORM / "api" / "farm_scope.py", "load_farm_scope"))
    assert isinstance(flag, ast.If) and ast.unparse(flag.test) == "not enforcement_requested()"
    assert len(flag.body) == 1 and _is_returns_false(flag.body)
    assert isinstance(probe, ast.If) and ast.unparse(probe.test) == "not await schema_present(conn)"
    assert _is_returns_false(probe.body)
    assert not [
        n for n in ast.walk(flag) if isinstance(n, ast.Attribute) and ast.unparse(n.value) == "conn"
    ]


def test_load_farm_scope_hydrates_only_from_the_grant_read_keyed_by_the_jwt_sub():
    body = _body(_function(PLATFORM / "api" / "farm_scope.py", "load_farm_scope"))[2:]
    reads = [
        i
        for i, s in enumerate(body)
        for n in ast.walk(s)
        if isinstance(n, ast.Call) and ast.unparse(n.func) == "conn.fetch"
    ]
    assert len(reads) == 1, "exactly one grant read"
    (read,) = [
        n
        for n in ast.walk(body[reads[0]])
        if isinstance(n, ast.Call) and ast.unparse(n.func) == "conn.fetch"
    ]
    assert [ast.unparse(a) for a in read.args] == [
        "_GRANTS",
        "str(user.tenant_id)",
        "str(user.user_id)",
    ], "the grant key is user.user_id, i.e. the JWT sub"
    writes = [
        i
        for i, s in enumerate(body)
        for n in ast.walk(s)
        if isinstance(n, ast.Attribute)
        and isinstance(n.ctx, ast.Store)
        and ast.unparse(n.value) == "user"
    ]
    assert {"farm_ids_access", "farm_access_all", "farm_scope_loaded"} <= {
        n.attr
        for s in body
        for n in ast.walk(s)
        if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
    }
    assert writes and min(writes) > reads[0], "the user is hydrated only after the read returns"
    last = body[-1]
    assert isinstance(last, ast.Return) and ast.unparse(last.value) == "True"
    assert "is_active" in farm_scope._GRANTS and "tenant_id = $1::uuid" in farm_scope._GRANTS


def test_v287_presence_is_cached_and_absence_is_asked_again():
    """Only a True probe sets the cache; nothing in a function ever caches absence."""
    fn = _function(PLATFORM / "api" / "farm_scope.py", "schema_present")
    stores = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ["_present"]
    ]
    assert [ast.unparse(s.value) for s in stores] == ["True"], "absence is never cached"
    (cached,) = [
        s for s in _body(fn) if isinstance(s, ast.If) and any(n in stores for n in ast.walk(s))
    ]
    assert ast.unparse(cached.test) == "await conn.fetchval(_PROBE) is True"
    tree = ast.parse((PLATFORM / "api" / "farm_scope.py").read_text(encoding="utf-8"))
    falses = [
        n
        for f in ast.walk(tree)
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
        for n in ast.walk(f)
        if isinstance(n, ast.Assign)
        and "_present" in [ast.unparse(t) for t in n.targets]
        and ast.unparse(n.value) != "True"
    ]
    assert falses == []


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


# ── no error-catching; no DDL from a request ──────────────────────────────────


def _source_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def test_farm_scope_detects_schema_by_catalog_probe_and_catches_nothing():
    """A caught 42P01 would abort the RLS transaction; presence is asked of the catalog."""
    tree = _source_tree(PLATFORM / "api" / "farm_scope.py")
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Try)], "no try/except at all"
    text = (PLATFORM / "api" / "farm_scope.py").read_text(encoding="utf-8")
    assert "UndefinedTable" not in text and "42P01" not in text


_DDL = re.compile(
    r"\b(CREATE|ALTER|DROP|GRANT|REVOKE|TRUNCATE|COMMENT\s+ON|SET\s+ROLE|RESET\s+ROLE"
    r"|SET\s+SESSION\s+AUTHORIZATION)\b",
    re.IGNORECASE,
)


def _docstrings(tree: ast.AST) -> set[int]:
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = n.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                out.add(id(body[0].value))
    return out


def _sql_constants(node: ast.AST) -> list[str]:
    """Every string literal except docstrings: any of them could be sent to the database."""
    skip = _docstrings(node)
    return [
        n.value
        for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip
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
    callers = sorted(
        str(p.relative_to(ROOT))
        for base in (PLATFORM, ROOT / "scripts")
        for p in base.rglob("*.py")
        if "tests" not in p.parts
        and p.name != "farm_scope.py"
        and "insert_tenant_grants" in p.read_text(encoding="utf-8")
    )
    assert callers == ["scripts/ops/farm_access_backfill.py"], callers


# ── review finding 3: every farm-scope consumer goes through farm_restriction ──


def test_the_regional_bulletin_keeps_owner_wide_access_with_partial_grants():
    """load_farm_scope fills farm_ids_access for owners too; the old "empty = all" rule then
    narrowed an owner holding one grant to that farm."""
    from api.routers.regional_bulletin import _farm_scope

    assert _farm_scope(_hydrated(UserRole.OWNER, ["farm-a"], all_farms=True)) is None
    assert _farm_scope(_hydrated(UserRole.WORKER, ["farm-a"])) == ["farm-a"]
    assert _farm_scope(_hydrated(UserRole.WORKER, [])) == [], "hydrated, no grant: no farm"
    assert _farm_scope(_user(UserRole.WORKER)) is None, "legacy unhydrated: every farm"


def test_the_regional_bulletin_keeps_farm_less_fields_for_a_restricted_user():
    """v287 keeps farm-less rows visible to the tenant; ``farm_id = ANY(...)`` is NULL for
    them, so the bulletin's own filter dropped them for anyone with a grant."""
    from api.routers.regional_bulletin import _BULLETIN_SQL

    assert "f.farm_id IS NULL OR f.farm_id = ANY($1::text[])" in _BULLETIN_SQL


def test_no_platform_code_reads_farm_ids_access_outside_the_authorization_core():
    """The only readers of the raw list are core.authorization (farm_restriction and its
    callers) and api.farm_scope (which fills it); everything else asks farm_restriction."""
    readers = sorted(
        str(p.relative_to(PLATFORM))
        for p in PLATFORM.rglob("*.py")
        if "tests" not in p.parts
        and re.search(
            r"\.farm_ids_access\b|[\"']farm_ids_access[\"']", p.read_text(encoding="utf-8")
        )
    )
    assert readers == ["api/farm_scope.py", "core/authorization.py"], readers


# ── review nit 5: every GUC the request path sets is transaction-local ────────

_SET_CONFIG = re.compile(r"set_config\(\s*'([a-zA-Z_.]+)'\s*,\s*[^,]*,\s*(true|false)\s*\)", re.I)


def _set_configs(node: ast.AST) -> list[tuple[str, str]]:
    return [
        (m.group(1), m.group(2).lower())
        for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        for m in _SET_CONFIG.finditer(n.value)
    ]


def test_every_set_config_on_the_request_path_is_transaction_local():
    """asyncpg's RESET ALL on release would hide a session-level set_config from a pooled-leak
    test, so the is_local flag itself is pinned here (and proven live without the reset)."""
    tenant_connection = next(
        n
        for n in _source_tree(MAIN).body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "tenant_connection"
    )
    calls = _set_configs(tenant_connection) + _set_configs(
        _source_tree(PLATFORM / "api" / "farm_scope.py")
    )
    names = {name for name, _ in calls}
    assert {"app.current_tenant", "app.current_user_id", "app.current_role"} <= names
    assert "app.enforce_farm_scope" in names
    assert all(local == "true" for _, local in calls), calls
