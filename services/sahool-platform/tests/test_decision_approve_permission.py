"""WX-10.7 — DECISION_APPROVE authz matrix + facade pass-through (unit, no network)."""

from __future__ import annotations

import api.decision_service_client as client
import pytest
from core.authorization import Permission, has_permission
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit


def _user(role):
    return UserSchema(
        user_id="u", tenant_id="00000000-0000-0000-0000-000000000002", role=role, name_ar="x"
    )


@pytest.mark.parametrize("role", [UserRole.OWNER, UserRole.MANAGER, UserRole.AGRONOMIST])
def test_reviewer_roles_have_decision_approve(role):
    assert has_permission(_user(role), Permission.DECISION_APPROVE) is True


@pytest.mark.parametrize("role", [UserRole.WORKER, UserRole.VIEWER])
def test_non_reviewer_roles_lack_decision_approve(role):
    assert has_permission(_user(role), Permission.DECISION_APPROVE) is False


def test_decision_approve_permission_value():
    assert Permission.DECISION_APPROVE.value == "decision:approve"


def test_headers_include_reviewed_by():
    h = client.decision_service_headers(tenant_id="t1", reviewed_by="rev-1")
    assert h["X-Reviewed-By"] == "rev-1" and h["X-Tenant-Id"] == "t1"
    # absent when not supplied.
    assert "X-Reviewed-By" not in client.decision_service_headers(tenant_id="t1")


def test_decision_transport_uses_service_bearer_and_preserves_actor(monkeypatch):
    monkeypatch.setenv("DECISION_SERVICE_TOKEN", "decision-only-secret")
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "different-agent-secret")
    h = client.decision_service_headers(
        tenant_id="t1", authorization="Bearer user-jwt", reviewed_by="rev-1"
    )
    assert h["Authorization"] == "Bearer decision-only-secret"
    assert h["X-Tenant-Id"] == "t1"
    assert h["X-Reviewed-By"] == "rev-1"
    assert "X-Agent-Token" not in h
    assert "user-jwt" not in repr(h)


@pytest.mark.parametrize("mode", ["production", "prod"])
def test_missing_decision_credential_cannot_fall_back_to_user_or_agent(monkeypatch, mode):
    from fastapi import HTTPException

    monkeypatch.setenv("SAHOOL_ENV", mode)
    monkeypatch.delenv("DECISION_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "wrong-purpose-secret")
    with pytest.raises(HTTPException) as exc:
        client.decision_service_headers(tenant_id="t1", authorization="Bearer user-jwt")
    assert exc.value.status_code == 503
    assert "decision_service_auth_unavailable" in str(exc.value.detail)
    assert "wrong-purpose-secret" not in str(exc.value.detail)


@pytest.mark.parametrize("role", list(UserRole))
@pytest.mark.parametrize("active", [True, False])
def test_session_permission_projection_uses_canonical_policy(role, active):
    from dataclasses import replace

    from api.routers.auth import auth_me

    user = replace(_user(role), is_active=active)
    projected = auth_me(user)["user"]
    assert projected["tenant_id"] == user.tenant_id
    assert projected["permissions"] == sorted(
        permission.value for permission in Permission if has_permission(user, permission)
    )
    if not active or role is UserRole.PLATFORM_ADMIN:
        assert "recommendation:view" not in projected["permissions"]


@pytest.mark.asyncio
async def test_facade_review_posts_to_review_path(monkeypatch):
    seen = {}

    async def fake_post(path, payload, *, tenant_id=None, reviewed_by=None, timeout_s=20.0):
        seen.update(path=path, tenant_id=tenant_id, reviewed_by=reviewed_by, payload=payload)
        return {"authoritative": True, "persisted": True}

    monkeypatch.setattr(client, "decision_post_json", fake_post)
    out = await client.review_decision(
        "dec_9", {"action": "approve"}, tenant_id="t1", reviewed_by="rev-1"
    )
    assert out["authoritative"] is True
    assert seen["path"] == "/v1/decisions/dec_9/review"
    assert seen["tenant_id"] == "t1" and seen["reviewed_by"] == "rev-1"
    # the facade must NOT synthesize authoritative/persisted — it only transports.
    assert "authoritative" not in seen["payload"]
