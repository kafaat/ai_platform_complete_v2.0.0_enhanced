from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# ``main`` وTestClient يستوردان fastapi؛ وظيفتا CI للوحدة/التكامل (منطق صرف على
# tests_v9) لا تُثبّتان fastapi، فنتخطّى الوحدة بأمان عند غيابها بدل كسر الجمع
# (نفس نمط حارس V57). محليّاً/حيث fastapi متاح تعمل الاختبارات كاملةً.
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist.main import app  # noqa: E402

# SEC-3: /approvals/* are now internal write endpoints guarded by the trusted
# service token (X-Agent-Token == SAHOOL_AGENT_TOKEN). Tests provision the secret
# and send the header — the correct new contract, assertions unchanged.
_AGENT_TOKEN = "test-agent-token-sec3"
_AUTH_HEADERS = {"X-Agent-Token": _AGENT_TOKEN}


@pytest.fixture(autouse=True)
def _provision_agent_token(monkeypatch):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", _AGENT_TOKEN)


def _pending_request():
    return {
        "id": "req-1",
        "tool": "request_imagery_backfill",
        "params": {"field_id": "field-1", "months": 24},
        "tenant_id": "tenant-1",
        "actor": "ai_agronomist",
        "risk": "medium",
        "capability": "can_trigger_backfill",
        "status": "pending",
        "requested_at": "2026-07-01T00:00:00Z",
        "decided_by": None,
        "decided_at": None,
        "deny_reason": None,
    }


def test_approval_endpoint_normalizes_decision_without_executing_tool():
    client = TestClient(app)
    resp = client.post(
        "/approvals/approve",
        json={"approval": _pending_request(), "approver": "user-1"},
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "approved"
    assert payload["executes_tool"] is False
    assert payload["approval"]["status"] == "approved"
    assert payload["approval"]["decided_by"] == "user-1"


def test_deny_endpoint_normalizes_decision_without_executing_tool():
    client = TestClient(app)
    resp = client.post(
        "/approvals/deny",
        json={"approval": _pending_request(), "approver": "user-1", "reason": "not_now"},
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "denied"
    assert payload["executes_tool"] is False
    assert payload["approval"]["status"] == "denied"
    assert payload["approval"]["deny_reason"] == "not_now"
