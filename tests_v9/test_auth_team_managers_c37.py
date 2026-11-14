"""C-37: the three tenant team routes admit exactly the roles that may invite.

Self-registration creates ``owner`` and invitations are sent by owner/admin
(``main.INVITER_ROLES``), so the team routes in ``routers/users.py`` must admit the same
two roles, and never ``platform_admin`` (auth has no cross-tenant identity).
The behaviour itself (tenant scope, 404 across tenants, protected peers, grantable
roles) is measured on live PostgreSQL in ``test_auth_admin_tenant_scope_live_pg.py``.
This file is the pure, always-on part: it reads the source, it does not import the app.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
USERS = ROOT / "services/auth/routers/users.py"
MAIN = ROOT / "services/auth/main.py"
HANDLERS = ("list_users", "change_role", "deactivate_user")


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _module_tuple(tree: ast.Module, name: str) -> tuple[str, ...]:
    for node in tree.body:
        target = getattr(node, "target", None) or (getattr(node, "targets", None) or [None])[0]
        if isinstance(target, ast.Name) and target.id == name:
            return tuple(ast.literal_eval(node.value))
    raise AssertionError(f"{name} not found")


def _inviter_roles() -> frozenset[str]:
    for node in _tree(MAIN).body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "INVITER_ROLES":
            call = node.value
            assert isinstance(call, ast.Call) and call.func.id == "frozenset"
            return frozenset(ast.literal_eval(call.args[0]))
    raise AssertionError("INVITER_ROLES not found in auth main.py")


def _require_role_args(fn: ast.AsyncFunctionDef) -> list[list[ast.expr]]:
    return [
        n.args
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "require_role"
    ]


def test_team_managers_are_the_inviter_roles_and_exclude_platform_admin():
    managers = _module_tuple(_tree(USERS), "_TEAM_MANAGERS")
    assert set(managers) == _inviter_roles() == {"owner", "admin"}
    assert "platform_admin" not in managers


@pytest.mark.parametrize("handler", HANDLERS)
def test_each_team_route_requires_the_team_managers(handler):
    fns = [
        n
        for n in ast.walk(_tree(USERS))
        if isinstance(n, ast.AsyncFunctionDef) and n.name == handler
    ]
    assert len(fns) == 1, handler
    calls = _require_role_args(fns[0])
    assert len(calls) == 1, (handler, len(calls))
    (args,) = calls
    # require_role(*_TEAM_MANAGERS): one source of truth, not a literal that can drift.
    assert len(args) == 1 and isinstance(args[0], ast.Starred), ast.dump(args[0])
    assert getattr(args[0].value, "id", "") == "_TEAM_MANAGERS", ast.dump(args[0])
