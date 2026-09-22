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

# SEC-3: /v1/approvals/* are now internal write endpoints guarded by the trusted
# service token (X-Agent-Token == SAHOOL_AGENT_TOKEN). Tests provision the secret
# and send the header — the correct new contract, assertions unchanged.
_AGENT_TOKEN = "test-agent-token-sec3"
_AUTH_HEADERS = {
    "X-Tenant-Id": "tenant-1",
    "X-User-Id": "user-1",
}  # SEC-3/3.1: approvals require gateway tenant + user


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


@pytest.fixture
def seeded():
    """يزرع الطلبَ في المخزن الخادميّ — **العقدُ تغيّر مع D01**.

    كان الشاهدان أدناه يُرسلان `_pending_request()` في الجسم **بلا زرعٍ خادميّ**
    ويتوقّعان `200`. وذاك كان يُرسّخ العطلَ نفسَه الذي أمسكه التدقيق: جسمُ الطلب
    يصير سجلَّ موافقةٍ من العدم. فالتهيئةُ هي ما تغيّر، **لا التأكيدات** — نيّةُ
    الشاهدين («يُطبِّع القرارَ ولا يُنفّذ الأداة») محفوظةٌ كما هي.
    """
    from services.ai_agronomist.main import _APPROVAL_STORE

    record = _pending_request()
    _APPROVAL_STORE.save(record)
    return record


def test_approval_endpoint_normalizes_decision_without_executing_tool(seeded):
    client = TestClient(app)
    resp = client.post(
        "/v1/approvals/approve",
        json={"approval": {"id": seeded["id"]}, "approver": "user-1"},
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "approved"
    assert payload["executes_tool"] is False
    assert payload["approval"]["status"] == "approved"
    assert payload["approval"]["decided_by"] == "user-1"


def test_deny_endpoint_normalizes_decision_without_executing_tool(seeded):
    client = TestClient(app)
    resp = client.post(
        "/v1/approvals/deny",
        json={"approval": {"id": seeded["id"]}, "approver": "user-1", "reason": "not_now"},
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "denied"
    assert payload["executes_tool"] is False
    assert payload["approval"]["status"] == "denied"
    assert payload["approval"]["deny_reason"] == "not_now"


# ─── D01: الموافقةُ مربوطةٌ بملكيّة السجلّ وبنسخته الخادميّة ────────────────────
#
# ستّةُ سيناريوهاتٍ سمّاها التدقيقُ الموحَّد (AP-01/04/05/06/07/08). وهي ليست ستَّ
# ثغراتٍ مستقلّة بل أثرُ غياب رابطٍ واحد: السجلُّ لم يكن يُقرأ بـ(المستأجِر، الهويّة)،
# ولم تكن حقولُه الخادميّةُ محميّةً من الدمج.

_OTHER_TENANT = {"X-Tenant-Id": "tenant-2", "X-User-Id": "user-2"}


def test_another_tenant_cannot_approve_a_record_it_does_not_own(seeded):
    """AP-01 — أثقلُها: مستأجِرٌ يوافق على سجلّ غيره."""
    client = TestClient(app)
    resp = client.post(
        "/v1/approvals/approve",
        json={"approval": {"id": seeded["id"]}, "approver": "user-2"},
        headers=_OTHER_TENANT,
    )
    assert resp.status_code == 404, "مستأجِرٌ قرّر في سجلّ غيره"


def test_another_tenant_cannot_deny_a_record_it_does_not_own(seeded):
    client = TestClient(app)
    resp = client.post(
        "/v1/approvals/deny",
        json={"approval": {"id": seeded["id"]}, "approver": "user-2", "reason": "x"},
        headers=_OTHER_TENANT,
    )
    assert resp.status_code == 404


def test_a_record_the_server_never_created_is_not_decidable():
    """AP-04 — كان جسمُ الطلب يصير سجلّاً؛ الآن لا سجلَّ ⇒ لا قرار."""
    client = TestClient(app)
    resp = client.post(
        "/v1/approvals/approve",
        json={"approval": {"id": "never-created-by-the-server"}, "approver": "user-1"},
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 404, "قُرِّر في طلبٍ لم يُنشئه الخادم"


def test_the_body_cannot_reopen_a_denied_record(seeded):
    """AP-05/06 — إعادةُ `denied` إلى `pending` من الجسم ثمّ الموافقة."""
    from services.ai_agronomist.main import _APPROVAL_STORE

    denied = dict(seeded)
    denied["status"] = "denied"
    _APPROVAL_STORE.save(denied)

    client = TestClient(app)
    resp = client.post(
        "/v1/approvals/approve",
        # الجسمُ يحاول إعادةَ الحالة إلى pending
        json={"approval": {"id": seeded["id"], "status": "pending"}, "approver": "user-1"},
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 409, "أُعيد سجلٌّ مرفوضٌ إلى pending من جسم الطلب"


def test_the_body_cannot_swap_the_params_the_hash_was_taken_over(seeded):
    """AP-07/08 — أخبثُها: تبديلُ `field_id` مع بقاء `input_hash` القديم.

    فتصير الموافقةُ على **مدخلٍ غيرِ الذي بُصِم**: الحقلُ المُنفَّذُ عليه ليس الحقلَ
    الذي رآه الإنسانُ حين وافق.
    """
    client = TestClient(app)
    resp = client.post(
        "/v1/approvals/approve",
        json={
            "approval": {"id": seeded["id"], "params": {"field_id": "field-OTHER"}},
            "approver": "user-1",
        },
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 200
    approved = resp.json()["approval"]
    assert approved["params"]["field_id"] == "field-1", "بُدِّل المدخلُ من جسم الطلب"


def test_another_tenant_cannot_resume_an_approved_envelope(seeded):
    """الاستئنافُ يخضع للملكيّة كالقرار — كان يقرأ بالهويّة وحدَها."""
    from services.ai_agronomist.main import _APPROVAL_STORE

    approved = dict(seeded)
    approved["status"] = "approved"
    _APPROVAL_STORE.save(approved)

    client = TestClient(app)
    resp = client.post(
        "/v1/approvals/resume",
        json={"approval_id": seeded["id"]},
        headers=_OTHER_TENANT,
    )
    assert resp.status_code == 404, "استُؤنِف مظروفُ موافقةٍ لمستأجِرٍ آخر"
