"""Functional tests (CI-enforced) for the newly-wired live endpoints:
irrigation water-analysis + pest-escalation (durable workflow + HIL).

تقوية: الفجوة كانت «الوحدات معزولة — لا endpoint يستدعيها». هذه الاختبارات
تضرب HTTP فعليّاً (TestClient) عبر التفويض، فتُثبِت أنّ الوصل حيّ لا ادّعاء:
- irrigation: SAR/RSC يُحسبان ويُعادان عبر الـAPI.
- pest: التدفّق يُعلَّق عند الموافقة (HIL) ثمّ يُستأنف فينفّذ — durable عبر طلبين.
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

    # ② نداء ثانٍ بنفس workflow_id + موافقة الخبير ⇒ يُستأنف (durable). W0-01: الموافقة
    # وحدها لا ترشّ؛ بوّابة guardrails من الخادم لا تجد أدلّة المبيد (مادّة/جرعة/اقتصاد)
    # فتحجب التنفيذ (fail-closed) بدل أن ينفّذ بلا فحص كيميائيّ.
    r2 = client.post(
        "/api/v1/pest-escalation/run",
        json={"workflow_id": wf, "approval_status": "approved"},
        headers=_auth(token),
    )
    assert r2.status_code == 200, r2.text
    b2 = r2.json()
    assert b2["workflow"]["status"] == "completed", b2["workflow"]
    execute = b2["step_results"]["execute"]
    assert execute["executed"] is False, f"executed without a guardrails allow: {execute}"
    assert execute["blocked_by"] == "guardrails", execute
    assert execute["guardrails"]["allowed"] is False, execute
    assert execute["guardrails"]["status"] == "evidence_unavailable", execute
    assert b2["step_results"]["follow_up"]["follow_up_scheduled"] is False, b2["step_results"]


def _run_approved(client, token) -> dict:
    wf = f"pest-{uuid.uuid4()}"
    r1 = client.post(
        "/api/v1/pest-escalation/run",
        json={"workflow_id": wf, "pest_type": "صدأ", "severity": 0.85},
        headers=_auth(token),
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["workflow"]["status"] == "suspended", r1.text
    r2 = client.post(
        "/api/v1/pest-escalation/run",
        json={"workflow_id": wf, "approval_status": "approved"},
        headers=_auth(token),
    )
    assert r2.status_code == 200, r2.text
    return r2.json()


@pytest.mark.integration
@pytest.mark.parametrize(
    "verdict",
    [
        {"allowed": False, "status": "denied", "reason_ar": "محظور"},
        {"allowed": False, "status": "unauthorized", "http_status": 401},
        {"allowed": False, "status": "timeout"},
        {"allowed": "true", "status": "allowed"},  # ليس True حرفيّاً ⇒ حجب
    ],
    ids=["deny", "401", "timeout", "truthy-not-true"],
)
def test_pest_escalation_execute_blocked_unless_guardrails_allowed(
    client_and_token, monkeypatch, verdict
):
    """W0-01: أيّ حكم guardrails غير allowed is True يحجب التنفيذ بعد موافقة الخبير."""
    import core.pest_escalation_flow as gate

    seen: list[dict] = []

    def _fake(ctx, *, tenant_id, user_id, **_kw):
        seen.append({"tenant_id": tenant_id, "action_type": ctx.get("action_type")})
        return dict(verdict)

    monkeypatch.setattr(gate, "evaluate_pesticide_guardrails", _fake)
    client, token = client_and_token
    body = _run_approved(client, token)
    execute = body["step_results"]["execute"]
    assert seen and seen[0]["action_type"] == "urgent_spray", seen
    assert execute["executed"] is False, f"executed on verdict {verdict}: {execute}"
    assert execute["blocked_by"] == "guardrails", execute


@pytest.mark.integration
def test_pest_escalation_executes_only_on_server_guardrails_allow(client_and_token, monkeypatch):
    """الضابط الموجب للبوّابة: حكم guardrails allowed is True من الخادم يتجاوز الحجب.

    PEST-EXECUTE-DEFAULT-ACK-01: المسار لا يوصل منفّذاً اليوم، فلا يُعلَن التنفيذ: الخادم
    يعيد executed=False بسبب executor_not_configured (لا مرجع مختلَق exec-<action>) ولا
    تُجدوَل متابعة. كان يعيد executed=True بمرجع افتراضيّ ويجدول متابعة لرشّ لم يقع.
    """
    import core.pest_escalation_flow as gate

    monkeypatch.setattr(
        gate,
        "evaluate_pesticide_guardrails",
        lambda ctx, **_kw: {"allowed": True, "status": "allowed", "reason_ar": "سمح"},
    )
    client, token = client_and_token
    body = _run_approved(client, token)
    execute = body["step_results"]["execute"]
    assert execute.get("blocked_by") is None, f"an allowed verdict must not block: {execute}"
    assert execute["guardrails"]["status"] == "allowed", execute
    assert execute["executed"] is False, f"no executor wired ⇒ not executed: {execute}"
    assert execute["reason"] == "executor_not_configured", execute
    assert not execute.get("execution_ref"), f"no made-up execution ref: {execute}"
    follow_up = body["step_results"]["follow_up"]
    assert follow_up["follow_up_scheduled"] is False, f"no follow-up without execution: {follow_up}"
