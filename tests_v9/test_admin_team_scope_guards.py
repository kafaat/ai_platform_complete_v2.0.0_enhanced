"""Source-level guards: tenant team API must not become global identity writer."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
USERS = (ROOT / "services/auth/routers/users.py").read_text(encoding="utf-8")
DENIALS = (ROOT / "services/sahool-platform/api/routers/security_audit.py").read_text(encoding="utf-8")
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
    assert USERS.index("await main.revoke_all_user_sessions(user_id)") < USERS.index("UPDATE users SET role=")
    assert "if main._redis is None:" in USERS


def test_denial_endpoint_scoped():
    assert "AUDIT.recent(limit=limit, tenant_id=tenant_id)" in DENIALS
    assert "AUDIT.summary(tenant_id=tenant_id)" in DENIALS


def test_invite_accept_is_one_transaction_and_row_locked():
    assert "async with main._acquire() as conn, conn.transaction():" in INV
    assert "FOR UPDATE" in INV
    assert "AND status='pending' RETURNING id" in INV
