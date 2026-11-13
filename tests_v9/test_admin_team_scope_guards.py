"""Source-level guards: tenant team API must not become global identity writer."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
USERS = (ROOT / "services/auth/routers/users.py").read_text(encoding="utf-8")
DENIALS_PATH = ROOT / "services/sahool-platform/api/routers/security_audit.py"
DENIALS = DENIALS_PATH.read_text(encoding="utf-8")
INV = (ROOT / "services/auth/routers/invitations.py").read_text(encoding="utf-8")


def test_users_list_scoped():
    assert "FROM users WHERE tenant_id=$1::uuid ORDER BY id" in USERS
    assert "_validate_team_actor(conn, admin)" in USERS


def test_team_changes_scope_target_and_never_promote_admin():
    assert USERS.count("WHERE id=$1 AND tenant_id=$2::uuid FOR UPDATE") == 2
    assert "role NOT IN ('owner','admin')" in USERS
    assert "not main.is_inviteable_role(role)" in USERS


def test_invalidation_before_update():
    assert USERS.count("await main.revoke_all_user_sessions(user_id)") == 2
    assert USERS.index("await main.revoke_all_user_sessions(user_id)") < USERS.index(
        "UPDATE users SET role="
    )
    assert "if main._redis is None:" in USERS


def test_denial_endpoint_scoped():
    assert "AUDIT.recent(limit=limit, tenant_id=tenant_id)" in DENIALS
    assert "AUDIT.summary(tenant_id=tenant_id)" in DENIALS


def test_invite_accept_is_one_transaction_and_row_locked():
    assert "async with main._acquire() as conn, conn.transaction():" in INV
    assert "FOR UPDATE" in INV
    assert "AND status='pending' RETURNING id" in INV


def _load_live_validator_from_source():
    """Execute the real authorization helper with a fake DB connection."""
    import ast
    from uuid import UUID

    from fastapi import HTTPException

    source = ast.parse(USERS)
    func = next(
        node
        for node in source.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_validate_team_actor"
    )
    module = ast.fix_missing_locations(ast.Module(body=[func], type_ignores=[]))
    scope = {"UUID": UUID, "HTTPException": HTTPException}
    exec(compile(module, "services/auth/routers/users.py", "exec"), scope)
    return scope["_validate_team_actor"]


class FakeTeamConnection:
    def __init__(self, row):
        self.row = row
        self.last_sql = None

    async def fetchrow(self, sql, *args):
        self.last_sql = sql
        assert args == (42, "11111111-1111-4111-8111-111111111111")
        return self.row


def test_team_validator_allows_active_owner_in_same_tenant():
    import asyncio

    validator = _load_live_validator_from_source()
    tenant = "11111111-1111-4111-8111-111111111111"
    conn = FakeTeamConnection({"role": "owner", "active": True})
    actor = {"sub": "42", "role": "owner", "tenant_id": tenant}

    assert asyncio.run(validator(conn, actor)) == tenant
    assert "WHERE id=$1 AND tenant_id=$2::uuid" in conn.last_sql


@pytest.mark.parametrize(
    ("row", "role"),
    [
        (None, "owner"),
        ({"role": "farmer", "active": True}, "admin"),
        ({"role": "owner", "active": False}, "owner"),
        ({"role": "manager", "active": True}, "manager"),
    ],
)
def test_team_validator_denies_missing_inactive_or_stale_membership(row, role):
    import asyncio

    from fastapi import HTTPException

    validator = _load_live_validator_from_source()
    tenant = "11111111-1111-4111-8111-111111111111"
    actor = {"sub": "42", "role": role, "tenant_id": tenant}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(validator(FakeTeamConnection(row), actor))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("tenant", ["", "not-a-uuid"])
def test_team_validator_denies_invalid_tenant_identity(tenant):
    import asyncio

    from fastapi import HTTPException

    validator = _load_live_validator_from_source()
    actor = {"sub": "42", "role": "owner", "tenant_id": tenant}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(validator(FakeTeamConnection(None), actor))
    assert exc.value.status_code == 403
