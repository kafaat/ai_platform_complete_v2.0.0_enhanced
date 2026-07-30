"""تحقّق V58.2a — مخازن الموافقة/التدقيق القابلة للاستبدال + استئناف الموافقة.

- ``InMemory*Store`` سلوك صحيح (save/get/list_pending/append/recent).
- ``build_*_store`` الافتراضيّ = memory؛ ``redis`` بلا اتّصال ⇒ سقوط آمن للذاكرة.
- ``RedisApprovalStore`` يعمل مع عميل مزيّف (يثبت مسار الاستمرار).
- نقطة ``/v1/approvals/resume``: تقرأ الموافقة المخزَّنة، تتطلّب حالة approved، وتُعيد
  مغلّف تنفيذ (لا تنفّذ داخل الـruntime) — مجهول/غير-موافَق ⇒ fail-closed.

منطق صرف عدا نقطة الـHTTP (importorskip) — وظيفة Unit Tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import agent_stores as S  # noqa: E402

# SEC-3: /v1/approvals/* now require the trusted internal service token
# (X-Agent-Token == SAHOOL_AGENT_TOKEN). The resume-endpoint tests provision the
# secret and send the header — the correct new contract, assertions unchanged.
_AGENT_TOKEN = "test-agent-token-sec3"
_AUTH_HEADERS = {
    "X-Tenant-Id": "tenant-1",
    "X-User-Id": "user-1",
}  # SEC-3/3.1: approvals require gateway tenant + user


def test_in_memory_approval_store_roundtrip():
    st = S.InMemoryApprovalStore()
    st.save({"id": "a1", "status": "pending_approval", "tool": "send_recommendation"})
    st.save({"id": "a2", "status": "approved", "tool": "create_prescription_map"})
    assert st.get("a1")["tool"] == "send_recommendation"
    assert st.get("missing") is None
    pending = st.list_pending()
    assert [p["id"] for p in pending] == ["a1"]  # only pending listed


def test_in_memory_audit_store_is_append_only_recent():
    st = S.InMemoryAuditStore()
    for i in range(5):
        st.append({"seq": i})
    assert [r["seq"] for r in st.recent(3)] == [2, 3, 4]


def test_build_defaults_to_memory(monkeypatch):
    monkeypatch.delenv("SAHOOL_AGENT_STORE_BACKEND", raising=False)
    assert isinstance(S.build_approval_store(), S.InMemoryApprovalStore)
    assert isinstance(S.build_audit_store(), S.InMemoryAuditStore)
    assert S.store_backend_name() == "memory"


def test_redis_backend_fails_safe_to_memory(monkeypatch):
    # redis requested but unreachable URL ⇒ never raise, fall back to memory.
    monkeypatch.setenv("SAHOOL_AGENT_STORE_BACKEND", "redis")
    monkeypatch.setenv("SAHOOL_AGENT_REDIS_URL", "redis://127.0.0.1:6390/0")
    assert isinstance(S.build_approval_store(), S.InMemoryApprovalStore)
    assert S.store_backend_name() == "memory"


class _FakeRedis:
    def __init__(self):
        self.kv = {}
        self.sets = {}

    def set(self, k, v, ex=None):
        self.kv[k] = v

    def get(self, k):
        return self.kv.get(k)

    def sadd(self, k, m):
        self.sets.setdefault(k, set()).add(m)

    def srem(self, k, m):
        self.sets.get(k, set()).discard(m)

    def smembers(self, k):
        return self.sets.get(k, set())


def test_redis_approval_store_with_fake_client():
    st = S.RedisApprovalStore(_FakeRedis())
    st.save({"id": "a1", "status": "pending_approval", "tool": "x"})
    assert st.get("a1")["tool"] == "x"
    assert [p["id"] for p in st.list_pending()] == ["a1"]
    st.save({"id": "a1", "status": "approved", "tool": "x"})  # decided ⇒ leaves pending set
    assert st.list_pending() == []


# ── /v1/approvals/resume endpoint (fastapi-guarded) ────────────────────────────
def test_resume_endpoint_reads_stored_approved_and_hands_off(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from services.ai_agronomist import main as M

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", _AGENT_TOKEN)
    client = TestClient(M.app)
    approval_obj = {
        "id": "req-xyz",
        "status": "pending",
        "tool": "create_prescription_map",
        "tenant_id": "t1",
        "params": {"field_id": "f1"},
        "input_hash": "h1",
    }
    # approve first (stores the approved record) ...
    ok = client.post(
        "/v1/approvals/approve",
        json={"approval": approval_obj, "approver": "u1"},
        headers=_AUTH_HEADERS,
    )
    assert ok.status_code == 200
    # ... then resume by id.
    r = client.post("/v1/approvals/resume", json={"approval_id": "req-xyz"}, headers=_AUTH_HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "resumed"
    assert body["resume"]["executes_in_chat_runtime"] is False
    assert body["resume"]["requires_domain_service"] is True


def test_resume_endpoint_fails_closed_on_unknown_id(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from services.ai_agronomist import main as M

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", _AGENT_TOKEN)
    r = TestClient(M.app).post(
        "/v1/approvals/resume", json={"approval_id": "nope-404"}, headers=_AUTH_HEADERS
    )
    assert r.status_code == 404
