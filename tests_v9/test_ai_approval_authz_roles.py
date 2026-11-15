"""Advisor approvals: who may decide, no self-approval, one resume per approval.

Before: approve / deny / resume only required *some* authenticated user of the tenant, so a
viewer or farmer could approve a mutating tool call, the user who asked for the action could
approve it, and one approval could be resumed any number of times.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from services.ai_agronomist import agent_stores as S  # noqa: E402
from services.ai_agronomist import approval_authz as A  # noqa: E402
from services.ai_agronomist import main as M  # noqa: E402

_TENANT = "tenant-1"


def _hdr(user: str = "approver-1", role: str | None = "expert") -> dict[str, str]:
    h = {"X-Tenant-Id": _TENANT, "X-User-Id": user}
    if role is not None:
        h["X-User-Role"] = role
    return h


def _record(rid: str = "apr_1", requested_by: str | None = "farmer-9") -> dict:
    return {
        "id": rid,
        "status": "pending",
        "tool": "create_prescription_map",
        "tenant_id": _TENANT,
        "params": {"field_id": "f1"},
        "input_hash": "h1",
        "requested_by": requested_by,
    }


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(M, "_APPROVAL_STORE", S.InMemoryApprovalStore())
    return TestClient(M.app)


@pytest.mark.parametrize("path", ["/v1/approvals/approve", "/v1/approvals/deny"])
@pytest.mark.parametrize("role", [None, "", "viewer", "farmer", "worker", "platform_admin", "x"])
def test_a_role_without_decision_approve_cannot_decide(client, path, role):
    M._APPROVAL_STORE.create(_record())
    r = client.post(path, json={"approval": {"id": "apr_1"}}, headers=_hdr(role=role))
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "approver_role_required"
    assert M._APPROVAL_STORE.get("apr_1")["status"] == "pending"  # nothing decided


@pytest.mark.parametrize("role", ["owner", "admin", "manager", "agronomist", "expert", "EXPERT"])
def test_roles_holding_decision_approve_can_approve(client, role):
    M._APPROVAL_STORE.create(_record())
    r = client.post(
        "/v1/approvals/approve", json={"approval": {"id": "apr_1"}}, headers=_hdr(role=role)
    )
    assert r.status_code == 200, r.text


def test_approver_roles_match_the_platform_decision_approve_matrix():
    """The advisor cannot import the platform, so the set is pinned against its role map."""
    platform_src = (ROOT / "services/sahool-platform/api/main.py").read_text(encoding="utf-8")
    authz_src = (ROOT / "services/sahool-platform/core/authorization.py").read_text(
        encoding="utf-8"
    )
    for name, platform_role in {
        "admin": "OWNER",
        "manager": "MANAGER",
        "agronomist": "AGRONOMIST",
        "expert": "AGRONOMIST",
    }.items():
        assert f'"{name}": UserRole.{platform_role},' in platform_src, name
    for refused in ("farmer", "worker", "viewer", "platform_admin"):
        assert refused not in A.APPROVER_ROLES, refused
    assert "Permission.DECISION_APPROVE" in authz_src


def test_the_requester_cannot_approve_their_own_request(client):
    M._APPROVAL_STORE.create(_record(requested_by="agro-7"))
    r = client.post(
        "/v1/approvals/approve", json={"approval": {"id": "apr_1"}}, headers=_hdr("agro-7")
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "self_approval_forbidden"
    assert M._APPROVAL_STORE.get("apr_1")["status"] == "pending"
    # The requester may still withdraw it (deny), and someone else may approve.
    other = client.post(
        "/v1/approvals/approve", json={"approval": {"id": "apr_1"}}, headers=_hdr("agro-8")
    )
    assert other.status_code == 200


def test_the_body_cannot_clear_requested_by(client):
    M._APPROVAL_STORE.create(_record(requested_by="agro-7"))
    r = client.post(
        "/v1/approvals/approve",
        json={"approval": {"id": "apr_1", "requested_by": "someone-else"}},
        headers=_hdr("agro-7"),
    )
    assert r.status_code == 403


def test_resume_is_single_use(client):
    M._APPROVAL_STORE.create(_record())
    assert (
        client.post(
            "/v1/approvals/approve", json={"approval": {"id": "apr_1"}}, headers=_hdr()
        ).status_code
        == 200
    )
    first = client.post("/v1/approvals/resume", json={"approval_id": "apr_1"}, headers=_hdr())
    assert first.status_code == 200
    stored = M._APPROVAL_STORE.get("apr_1")
    assert stored["status"] == A.STATUS_RESUMED and stored["resumed_by"] == "approver-1"
    second = client.post("/v1/approvals/resume", json={"approval_id": "apr_1"}, headers=_hdr())
    assert second.status_code == 409


def test_resume_needs_an_approver_role(client):
    M._APPROVAL_STORE.create(_record())
    client.post("/v1/approvals/approve", json={"approval": {"id": "apr_1"}}, headers=_hdr())
    r = client.post(
        "/v1/approvals/resume", json={"approval_id": "apr_1"}, headers=_hdr(role="viewer")
    )
    assert r.status_code == 403
    assert M._APPROVAL_STORE.get("apr_1")["status"] == "approved"


def test_chat_stamps_the_gateway_user_on_records_it_creates():
    saved: list[dict] = []
    save = A.stamp_requester(saved.append, " farmer-9 ")
    save({"id": "apr_x", "requested_by": "spoofed"})
    assert saved == [{"id": "apr_x", "requested_by": "farmer-9"}]
    A.stamp_requester(saved.append, None)({"id": "apr_y"})
    assert saved[-1]["requested_by"] is None  # service-token call: no human requester


def test_every_evidence_endpoint_passes_the_gateway_user():
    src = (ROOT / "services/ai_agronomist/main.py").read_text(encoding="utf-8")
    assert "save_pending_approval=stamp_requester(_save_pending_approval, x_user_id)" in src
    assert src.count('x_user_id: str | None = Header(default=None, alias="X-User-Id")') == 4
    assert src.count("x_user_id=x_user_id,") == 4


def test_resume_store_failure_is_503_and_writes_no_audit(client, monkeypatch):
    M._APPROVAL_STORE.create(_record())
    client.post("/v1/approvals/approve", json={"approval": {"id": "apr_1"}}, headers=_hdr())
    audits: list[dict] = []
    monkeypatch.setattr(M, "_save_agent_tool_audit", audits.append)

    def _boom(*_a, **_k):
        raise RuntimeError("redis down")

    monkeypatch.setattr(M._APPROVAL_STORE, "transition", _boom)
    r = client.post("/v1/approvals/resume", json={"approval_id": "apr_1"}, headers=_hdr())
    assert r.status_code == 503 and r.json()["detail"] == "approval_store_unavailable"
    assert audits == []  # no handoff recorded when uniqueness is unknown


def test_a_resume_that_loses_the_transition_race_is_409(client, monkeypatch):
    M._APPROVAL_STORE.create(_record())
    client.post("/v1/approvals/approve", json={"approval": {"id": "apr_1"}}, headers=_hdr())
    monkeypatch.setattr(M._APPROVAL_STORE, "transition", lambda *_a, **_k: False)
    r = client.post("/v1/approvals/resume", json={"approval_id": "apr_1"}, headers=_hdr())
    assert r.status_code == 409 and r.json()["detail"] == "approval_already_resumed"


@pytest.mark.parametrize("path", ["/v1/query", "/v1/chat", "/v1/explain", "/v1/recommend"])
def test_each_evidence_endpoint_stamps_the_gateway_user_on_a_created_record(
    client, monkeypatch, path
):
    async def _fake_runtime(req, **kw):
        kw["save_pending_approval"]({"id": "apr_chat", "tenant_id": _TENANT, "status": "pending"})
        return {"ok": True}

    monkeypatch.setattr(M, "_build_evidence_response_runtime", _fake_runtime)
    r = client.post(
        path,
        json={"question": "اسقِ الحقل؟"},
        headers={"X-Tenant-Id": _TENANT, "X-User-Id": "farmer-9"},
    )
    assert r.status_code == 200, r.text
    assert M._APPROVAL_STORE.get("apr_chat")["requested_by"] == "farmer-9"
