"""T11 (audit 2026-11-01): approval decisions merged ``user_id``/``session_id`` and the
decision stamps from the request body into the stored record; the resume audit then
recorded that caller-chosen identity. Identity must come from the gateway principal.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from services.ai_agronomist import main as M  # noqa: E402

_AUTH = {"X-Tenant-Id": "tenant-1", "X-User-Id": "user-1"}


@pytest.fixture
def seeded(monkeypatch):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "test-agent-token-t11")
    record = {
        "id": "req-t11",
        "tool": "request_imagery_backfill",
        "params": {"field_id": "field-1", "months": 24},
        "tenant_id": "tenant-1",
        "actor": "ai_agronomist",
        "risk": "medium",
        "capability": "can_trigger_backfill",
        "status": "pending",
        "requested_at": "2026-07-01T00:00:00Z",
        "result_summary": "pending_human_approval",
        "decided_by": None,
        "decided_at": None,
        "deny_reason": None,
    }
    M._APPROVAL_STORE.save(record)
    return record


_FORGED = {
    "user_id": "attacker",
    "session_id": "forged-session",
    "decided_by": "attacker",
    "requested_at": "1999-01-01T00:00:00Z",
    "result_summary": "forged",
    "deny_reason": "forged",
}


def test_t11_approve_body_cannot_set_audit_identity(seeded):
    client = TestClient(M.app)
    resp = client.post(
        "/v1/approvals/approve",
        json={"approval": {"id": seeded["id"], **_FORGED}, "approver": "attacker"},
        headers=_AUTH,
    )
    assert resp.status_code == 200
    approved = resp.json()["approval"]
    assert "user_id" not in approved and "session_id" not in approved
    assert approved["decided_by"] == "user-1"
    assert approved["requested_at"] == seeded["requested_at"]
    assert approved["result_summary"] == seeded["result_summary"]
    assert approved["deny_reason"] is None
    stored = M._APPROVAL_STORE.get(seeded["id"])
    assert "user_id" not in stored and "session_id" not in stored
    audit = M._AUDIT_STORE.recent(1)[-1]
    assert audit["outcome"] == "approved" and audit["user_id"] == "user-1"

    # The resume audit names the authenticated caller, not anything the body injected.
    resp = client.post("/v1/approvals/resume", json={"approval_id": seeded["id"]}, headers=_AUTH)
    assert resp.status_code == 200
    resumed = M._AUDIT_STORE.recent(1)[-1]
    assert resumed["outcome"] == "resumed_for_domain_execution"
    assert resumed["user_id"] == "user-1"
    assert resumed.get("session_id") != "forged-session"


def test_t11_deny_body_cannot_set_audit_identity(seeded):
    client = TestClient(M.app)
    resp = client.post(
        "/v1/approvals/deny",
        json={"approval": {"id": seeded["id"], **_FORGED}, "reason": "no"},
        headers=_AUTH,
    )
    assert resp.status_code == 200
    denied = resp.json()["approval"]
    assert "user_id" not in denied and "session_id" not in denied
    assert denied["decided_by"] == "user-1" and denied["deny_reason"] == "no"
    assert denied["requested_at"] == seeded["requested_at"]
    assert M._AUDIT_STORE.recent(1)[-1]["user_id"] == "user-1"
