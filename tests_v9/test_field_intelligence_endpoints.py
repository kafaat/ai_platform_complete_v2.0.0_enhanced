"""Functional tests (CI-enforced) for the newly-wired live endpoints:
irrigation water-analysis + pest-escalation (durable workflow + HIL).

تقوية: الفجوة كانت «الوحدات معزولة — لا endpoint يستدعيها». هذه الاختبارات
تضرب HTTP فعليّاً (TestClient) عبر التفويض، فتُثبِت أنّ الوصل حيّ لا ادّعاء:
- irrigation: SAR/RSC يُحسبان ويُعادان عبر الـAPI.
- pest: التدفّق يُعلَّق عند الموافقة ثمّ يُستأنف، ويبلّغ بصدق عن غياب منفّذ الرش.
"""

from __future__ import annotations

import os
import secrets
import sys
import uuid
from copy import deepcopy
from pathlib import Path

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


# Local HTTP witnesses: real authentication with in-memory stores and synthetic
# executor receipts. These do not certify deployed execution or PostgreSQL RLS.
@pytest.fixture
def pest_http_context(monkeypatch):
    """Use the project's real app/auth and its normal no-database store path."""
    signing_key = secrets.token_urlsafe(48)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.setenv("SAHOOL_JWT_SECRET", signing_key)
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    source_root = Path(__file__).resolve().parents[1]
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    for path in (source_root, source_root / "services" / "sahool-platform"):
        monkeypatch.syspath_prepend(str(path))

    from api import main
    from core.canonical_schemas import UserRole, UserSchema
    from core.jwt_denylist import InMemoryDenylist
    from fastapi.testclient import TestClient

    assert Path(main.__file__).resolve().is_relative_to(source_root)
    assert not main.app.dependency_overrides, "Auth dependencies must not be bypassed"
    # Other tests may have imported main before this fixture. Bind the cached
    # configuration too, while retaining the real token signer and verifier.
    monkeypatch.setattr(main, "JWT_SECRET", signing_key)
    monkeypatch.setattr(main, "JWT_VERIFY_KEY", signing_key)
    monkeypatch.setattr(main, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(main, "JWT_VERIFY_ALGORITHM", "HS256")
    monkeypatch.setattr(main, "_DENYLIST", InMemoryDenylist())
    stores_before = dict(main._INMEM_WORKFLOW_STORES)
    main._INMEM_WORKFLOW_STORES.clear()
    client = TestClient(main.app)

    def identity():
        user = UserSchema(
            user_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            role=UserRole.AGRONOMIST,
            name_ar="اختبار محلي مستقل",
        )
        token = main.create_token(user)
        return str(user.tenant_id), {"Authorization": f"Bearer {token}"}

    try:
        yield client, main, identity
    finally:
        client.close()
        main._INMEM_WORKFLOW_STORES.clear()
        main._INMEM_WORKFLOW_STORES.update(stores_before)


def _post_pest(client, headers, **payload):
    response = client.post("/api/v1/pest-escalation/run", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _inject_pest_executor(monkeypatch, executor):
    from core import pest_escalation_flow

    original = pest_escalation_flow.run_pest_escalation

    def run_with_local_executor(*args, **kwargs):
        return original(*args, execute_fn=executor, **kwargs)

    monkeypatch.setattr(pest_escalation_flow, "run_pest_escalation", run_with_local_executor)


@pytest.mark.unit
def test_positive_receipt_is_reported_and_http_replay_does_not_execute_twice(
    pest_http_context, monkeypatch
):
    client, main, identity = pest_http_context
    tenant, headers = identity()
    calls = []

    def executor(context):
        calls.append(context["action_type"])
        return {"executed": True, "execution_ref": "local-receipt-pr1521-positive"}

    _inject_pest_executor(monkeypatch, executor)
    workflow_id = f"positive-{uuid.uuid4()}"
    pending = _post_pest(client, headers, workflow_id=workflow_id, pest_type="locust", severity=0.9)
    assert pending["workflow"]["status"] == "suspended"
    assert pending["execution"]["status"] == "not_attempted"
    assert calls == []

    accepted = _post_pest(client, headers, workflow_id=workflow_id, approval_status="approved")
    assert accepted["workflow"]["status"] == "completed"
    assert accepted["execution"] == {
        "status": "executed",
        "executed": True,
        "execution_ref": "local-receipt-pr1521-positive",
        "reason": None,
    }
    assert accepted["step_results"]["follow_up"]["follow_up_scheduled"] is True
    assert calls == ["urgent_spray"]
    stored = deepcopy(main._get_workflow_store(tenant).load(workflow_id).to_dict())

    replay = _post_pest(client, headers, workflow_id=workflow_id, approval_status="approved")
    assert replay["execution"] == accepted["execution"]
    assert replay["step_results"] == accepted["step_results"]
    assert calls == ["urgent_spray"]
    assert main._get_workflow_store(tenant).load(workflow_id).to_dict() == stored


@pytest.mark.unit
def test_authenticated_tenants_with_same_workflow_id_keep_separate_http_state(pest_http_context):
    client, main, identity = pest_http_context
    tenant_a, headers_a = identity()
    tenant_b, headers_b = identity()
    workflow_id = f"tenant-shared-{uuid.uuid4()}"

    unauthenticated = client.post("/api/v1/pest-escalation/run", json={"workflow_id": workflow_id})
    assert unauthenticated.status_code == 401
    a_pending = _post_pest(
        client, headers_a, workflow_id=workflow_id, pest_type="tenant-a-locust", severity=0.9
    )
    assert a_pending["workflow"]["status"] == "suspended"
    a_saved = deepcopy(main._get_workflow_store(tenant_a).load(workflow_id).to_dict())

    b_finished = _post_pest(
        client, headers_b, workflow_id=workflow_id, pest_type="tenant-b-mite", severity=0.1
    )
    assert b_finished["workflow"]["status"] == "completed"
    assert b_finished["context"]["pest_type"] == "tenant-b-mite"
    assert b_finished["context"]["severity"] == 0.1
    assert b_finished["execution"]["executed"] is False
    assert main._get_workflow_store(tenant_a).load(workflow_id).to_dict() == a_saved
    b_saved = deepcopy(main._get_workflow_store(tenant_b).load(workflow_id).to_dict())

    a_finished = _post_pest(client, headers_a, workflow_id=workflow_id, approval_status="approved")
    assert a_finished["context"]["pest_type"] == "tenant-a-locust"
    assert a_finished["context"]["severity"] == 0.9
    assert a_finished["execution"]["reason"] == "executor_not_configured"
    assert main._get_workflow_store(tenant_b).load(workflow_id).to_dict() == b_saved
    assert a_saved["tenant_id"] == tenant_a
    assert b_saved["tenant_id"] == tenant_b


@pytest.mark.unit
def test_executor_exception_without_saved_receipt_stays_unknown_at_http_boundary(
    pest_http_context, monkeypatch
):
    client, _, identity = pest_http_context
    _, headers = identity()
    calls = []

    def executor(context):
        calls.append(context["action_type"])
        raise RuntimeError("synthetic local callback lost its receipt")

    _inject_pest_executor(monkeypatch, executor)
    workflow_id = f"lost-receipt-{uuid.uuid4()}"
    pending = _post_pest(client, headers, workflow_id=workflow_id, pest_type="locust", severity=0.9)
    assert pending["workflow"]["status"] == "suspended"
    assert calls == []
    failed = _post_pest(client, headers, workflow_id=workflow_id, approval_status="approved")
    assert failed["workflow"]["status"] == "compensated"
    assert failed["workflow"]["current_step"] == "execute"
    assert "execute" not in failed["step_results"]
    assert "follow_up" not in failed["step_results"]
    assert failed["execution"] == {
        "status": "reconciliation_required",
        "executed": None,
        "execution_ref": None,
        "reason": "execution_outcome_unknown",
    }
    replay = _post_pest(client, headers, workflow_id=workflow_id, approval_status="approved")
    assert replay["execution"] == failed["execution"]
    assert calls == ["urgent_spray"]
