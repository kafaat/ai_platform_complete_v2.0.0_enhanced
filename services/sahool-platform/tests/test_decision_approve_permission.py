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
