"""Team authorization regression tests."""

import ast
import asyncio
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TENANT = "11111111-1111-4111-8111-111111111111"
USERS_PATH = ROOT / "services/auth/routers/users.py"
DENIALS_PATH = ROOT / "services/sahool-platform/api/routers/security_audit.py"
INVITES_PATH = ROOT / "services/auth/routers/invitations.py"
USERS = USERS_PATH.read_text(encoding="utf-8")
DENIALS = DENIALS_PATH.read_text(encoding="utf-8")
INVITES = INVITES_PATH.read_text(encoding="utf-8")


def _team_validator():
    found = None
    for node in ast.parse(USERS).body:
        if isinstance(node, ast.AsyncFunctionDef):
            if node.name == "_validate_team_actor":
                found = node
                break
    if found is None:
        raise AssertionError("team validator missing")
    module = ast.Module(body=[found], type_ignores=[])
    scope = {"UUID": UUID, "HTTPException": HTTPException}
    compiled = compile(ast.fix_missing_locations(module), "users.py", "exec")
    exec(compiled, scope)
    return scope["_validate_team_actor"]


class FakeConnection:
    def __init__(self, row):
        self.row = row

    async def fetchrow(self, sql, *params):
        assert "tenant_id=$2::uuid" in sql
        assert params == (42, TENANT)
        return self.row


def _actor(role, tenant_id=TENANT):
    return {"sub": "42", "role": role, "tenant_id": tenant_id}


def test_users_list_has_tenant_predicate():
    assert "FROM users WHERE tenant_id=$1::uuid ORDER BY id" in USERS
    assert "_validate_team_actor(conn, admin)" in USERS


def test_privileged_role_mutation_rejected():
    assert "not main.is_inviteable_role(role)" in USERS
    assert "role NOT IN ('owner','admin')" in USERS
    assert USERS.count("WHERE id=$1 AND tenant_id=$2::uuid FOR UPDATE") == 2


def test_revoke_before_account_update():
    revoke = "await main.revoke_all_user_sessions(user_id)"
    assert USERS.count(revoke) == 2
    assert USERS.index(revoke) < USERS.index("UPDATE users SET role=")
    assert "if main._redis is None:" in USERS


def test_denial_endpoint_only_returns_tenant_records():
    assert "AUDIT.recent(limit=limit, tenant_id=tenant_id)" in DENIALS
    assert "AUDIT.summary(tenant_id=tenant_id)" in DENIALS


def test_invitation_consumption_is_atomic():
    assert "async with main._acquire() as conn, conn.transaction():" in INVITES
    assert "FOR UPDATE" in INVITES
    assert "AND status='pending' RETURNING id" in INVITES


@pytest.mark.parametrize("role", ["owner", "admin"])
def test_active_team_administrator_authorized(role):
    validator = _team_validator()
    row = {"role": role, "active": True}
    result = asyncio.run(validator(FakeConnection(row), _actor(role)))
    assert result == TENANT


@pytest.mark.parametrize(
    ("role", "row"),
    [
        ("owner", None),
        ("owner", {"role": "owner", "active": False}),
        ("admin", {"role": "farmer", "active": True}),
        ("manager", {"role": "manager", "active": True}),
    ],
)
def test_missing_inactive_and_stale_membership_denied(role, row):
    validator = _team_validator()
    with pytest.raises(HTTPException) as error:
        asyncio.run(validator(FakeConnection(row), _actor(role)))
    assert error.value.status_code == 403


@pytest.mark.parametrize("tenant_id", ["", "invalid-uuid"])
def test_invalid_tenant_identity_denied(tenant_id):
    validator = _team_validator()
    with pytest.raises(HTTPException) as error:
        asyncio.run(validator(FakeConnection(None), _actor("owner", tenant_id)))
    assert error.value.status_code == 403
