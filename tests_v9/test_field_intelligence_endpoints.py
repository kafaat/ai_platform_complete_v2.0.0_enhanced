"""Functional tests (CI-enforced) for the newly-wired live endpoints:
irrigation water-analysis + pest-escalation (durable workflow + HIL).

تقوية: الفجوة كانت «الوحدات معزولة — لا endpoint يستدعيها». هذه الاختبارات
تضرب HTTP فعليّاً (TestClient) عبر التفويض، فتُثبِت أنّ الوصل حيّ لا ادّعاء:
- irrigation: SAR/RSC يُحسبان ويُعادان عبر الـAPI.
- pest: التدفّق يُعلَّق عند الموافقة ثمّ يُستأنف، ويبلّغ بصدق عن غياب منفّذ الرش.
"""

from __future__ import annotations

import os
import sys
import uuid

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def client_and_token():
    os.environ.setdefault("JWT_SECRET", "test-secret-key-for-ci-only-0123456789")
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as m
    from core.canonical_schemas import UserRole, UserSchema
    from fastapi.testclient import TestClient

    user = UserSchema(
        user_id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),  # UUID صالح (المخزن المعمّر يحقن tenant)
        role=UserRole.AGRONOMIST,
        name_ar="مهندس اختبار",
    )
    token = m.create_token(user)
    # نضمن مسار InMemory (لا DATABASE_URL) ليصمد الاستئناف عبر الطلبات دون قاعدة.
    # نحفظ DATABASE_URL ونستعيده في التفكيك (لئلّا نكسر اختبارات تكامل أخرى تحتاجه
    # في نفس العمليّة مثل test_workflow_store).
    saved_dsn = os.environ.pop("DATABASE_URL", None)
    m._INMEM_WORKFLOW_STORES.clear()  # تصفير مخازن المستأجرين (حتميّة عبر الاختبارات)
    try:
        yield TestClient(m.app), token
    finally:
        if saved_dsn is not None:
            os.environ["DATABASE_URL"] = saved_dsn
        m._INMEM_WORKFLOW_STORES.clear()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
def test_irrigation_water_analysis_endpoint(client_and_token):
    client, token = client_and_token
    # عيّنة كاملة (FAO-29/USDA-197/USSL) — SAR/RSC يجب أن يُحسبا
    r = client.post(
        "/api/v1/irrigation/water-analysis",
        json={
            "sample_id": "w1",
            "na": 10.0,
            "ca": 4.0,
            "mg": 2.0,
            "hco3": 3.0,
            "co3": 0.0,
            "ec_dsm": 1.2,
        },
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["indices"]["sar"] is not None  # محسوب (لا نقص)
    assert body["indices"]["rsc_meq_l"] is not None
    assert body["data_complete"] is True


@pytest.mark.integration
def test_irrigation_requires_auth(client_and_token):
    client, _ = client_and_token
    r = client.post("/api/v1/irrigation/water-analysis", json={"sample_id": "w2"})
    assert r.status_code == 401  # fail-closed (سيادة الوصول)


@pytest.mark.integration
def test_pest_escalation_durable_hil(client_and_token):
    client, token = client_and_token
    wf = f"pest-{uuid.uuid4()}"
    # ① أوّل نداء: آفة مؤكّدة عالية ⇒ يصل للموافقة ثمّ يُعلَّق (HIL — لا تنفيذ بعد)
    r1 = client.post(
        "/api/v1/pest-escalation/run",
        json={"workflow_id": wf, "pest_type": "صدأ", "severity": 0.85},
        headers=_auth(token),
    )
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["workflow"]["status"] == "suspended"
    assert b1["step_results"].get("execute") is None  # لم يُنفَّذ قبل الموافقة

    # ② الموافقة تستأنف التدفّق؛ نقطة HTTP هذه لا توصل منفّذ رش.
    r2 = client.post(
        "/api/v1/pest-escalation/run",
        json={"workflow_id": wf, "approval_status": "approved"},
        headers=_auth(token),
    )
    assert r2.status_code == 200, r2.text
    b2 = r2.json()
    assert b2["workflow"]["status"] == "completed"
    assert b2["step_results"]["execute"] == {
        "executed": False,
        "execution_ref": None,
        "reason": "executor_not_configured",
    }
    assert b2["step_results"]["follow_up"] == {"follow_up_scheduled": False}
    assert b2["execution"] == {
        "status": "not_executed",
        "executed": False,
        "execution_ref": None,
        "reason": "executor_not_configured",
    }


@pytest.mark.integration
def test_pest_escalation_ambiguous_executor_ack_requires_reconciliation(
    client_and_token, monkeypatch
):
    from core import pest_escalation_flow

    client, token = client_and_token
    real_run = pest_escalation_flow.run_pest_escalation
    calls = []

    def executor_stub(context):
        calls.append(context["action_type"])
        return {}

    def run_with_stub(*args, **kwargs):
        return real_run(*args, execute_fn=executor_stub, **kwargs)

    monkeypatch.setattr(pest_escalation_flow, "run_pest_escalation", run_with_stub)
    workflow_id = f"pest-{uuid.uuid4()}"
    payload = {"workflow_id": workflow_id, "pest_type": "صدأ", "severity": 0.85}
    first = client.post("/api/v1/pest-escalation/run", json=payload, headers=_auth(token))
    assert first.status_code == 200, first.text
    assert first.json()["workflow"]["status"] == "suspended"
    assert calls == []

    result = client.post(
        "/api/v1/pest-escalation/run",
        json={"workflow_id": workflow_id, "approval_status": "approved"},
        headers=_auth(token),
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert len(calls) == 1
    assert body["execution"] == {
        "status": "reconciliation_required",
        "executed": None,
        "execution_ref": None,
        "reason": "execution_not_confirmed",
    }
    assert body["step_results"]["follow_up"] == {"follow_up_scheduled": False}


@pytest.mark.integration
@pytest.mark.parametrize("action", ["urgent_spray", "biocontrol"])
def test_completed_legacy_pest_receipt_requires_verification(client_and_token, monkeypatch, action):
    from copy import deepcopy

    from api.routers import pest_escalation
    from core.workflow_engine import InMemoryWorkflowStore, WorkflowState, WorkflowStatus

    client, token = client_and_token
    workflow_id = f"pest-{uuid.uuid4()}"
    receipt = {"executed": True, "execution_ref": f"exec-{action}"}
    follow_up = {"follow_up_scheduled": True}
    store = InMemoryWorkflowStore()
    state = WorkflowState(
        workflow_id=workflow_id,
        status=WorkflowStatus.COMPLETED,
        completed_steps=[
            "detect",
            "confirm",
            "recommend",
            "await_approval",
            "execute",
            "follow_up",
        ],
        step_results={"execute": receipt, "follow_up": follow_up},
        context={"action_type": action, **receipt, **follow_up},
    )
    store.save(state)
    original = deepcopy(state.to_dict())
    monkeypatch.setattr(pest_escalation, "_get_workflow_store", lambda tenant_id: store)
    monkeypatch.setattr(store, "save", lambda state: pytest.fail("completed workflow was replayed"))
    for _ in range(2):
        response = client.post(
            "/api/v1/pest-escalation/run",
            json={"workflow_id": workflow_id, "approval_status": "approved"},
            headers=_auth(token),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["workflow"]["status"] == "completed"
        assert body["execution"] == {
            "status": "reconciliation_required",
            "executed": None,
            "execution_ref": None,
            "reason": "legacy_synthetic_reference",
        }
        for view in (body["context"], body["step_results"]["execute"]):
            assert view["executed"] is None
            assert view["execution_ref"] is None
        assert store.load(workflow_id).to_dict() == original
