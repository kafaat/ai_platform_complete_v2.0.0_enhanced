"""W0-01: بوّابة السلامة الكيميائيّة لتصعيد الآفة من جهة الخادم (airuntime-1 / web-2).

قبلها: موافقة الخبير على مبيد تنفّذ دون أيّ فحص guardrails (المتصفّح كان يحصل على 401
والواجهة تفشل مفتوحة). هنا نقفل: التنفيذ لا يحدث إلّا إذا أعاد guardrails-engine
``allowed is True``؛ الرفض و401 و422 والمهلة وخطأ الشبكة والأدلّة الناقصة كلّها حجب.
لا قاعدة ولا شبكة: النقل HTTP مُستبدَل بـ``httpx.MockTransport``.
"""

from __future__ import annotations

import json

import httpx
import pytest
from core import pest_escalation_flow as gate
from core.pest_escalation_flow import build_pest_escalation_steps, run_pest_escalation
from core.workflow_engine import InMemoryWorkflowStore, WorkflowStatus

pytestmark = pytest.mark.unit

TENANT = "00000000-0000-0000-0000-0000000000a1"

# سياق تدفّق يحمل أدلّة المبيد كاملة (كما سيحقنها منشئ سياق الحوكمة W1-12 لاحقاً).
_EVIDENCE_CTX = {
    "approval_status": "approved",
    "action_type": "urgent_spray",
    "pest_type": "locust",
    "severity": 0.9,
    "field_id": "f-1",
    "chemical": "Spinosad",
    "dosage_kg_ha": 0.1,
    "cost_usd": 40.0,
    "projected_revenue_increase_usd": 300.0,
}
_FARM = {"annual_revenue_usd": 12000.0, "annual_costs_usd": 8000.0, "cash_reserve_usd": 900.0}


def _farm_fn(tenant_id, field_id):
    return dict(_FARM)


def _transport(status: int = 200, body: object = None, *, raise_exc: Exception | None = None):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if raise_exc is not None:
            raise raise_exc
        if isinstance(body, (bytes, str)):
            return httpx.Response(status, content=body)
        return httpx.Response(status, json=body if body is not None else {})

    return httpx.MockTransport(handler), calls


def _evaluate(transport, *, ctx=None, user_id="7", farm_fn=_farm_fn):
    return gate.evaluate_pesticide_guardrails(
        dict(ctx or _EVIDENCE_CTX),
        tenant_id=TENANT,
        user_id=user_id,
        farm_context_fn=farm_fn,
        transport=transport,
    )


@pytest.fixture(autouse=True)
def _service_env(monkeypatch):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "svc-token-for-tests")
    monkeypatch.setenv("GUARDRAILS_URL", "http://guardrails.test")


def test_allowed_true_is_the_only_allow_and_request_is_server_built():
    transport, calls = _transport(
        200, {"allowed": True, "overall_risk": "LOW", "requires_human_approval": False}
    )
    verdict = _evaluate(transport)
    assert verdict["allowed"] is True, verdict
    assert verdict["status"] == gate.ALLOWED, verdict
    assert len(calls) == 1, "exactly one server-side /v1/validate call expected"
    req = calls[0]
    assert str(req.url) == "http://guardrails.test/v1/validate", req.url
    assert req.headers.get("X-Agent-Token") == "svc-token-for-tests", "service token header missing"
    payload = json.loads(req.content)
    assert payload["action_type"] == "pesticide", payload
    assert payload["tenant_id"] == TENANT, payload
    assert payload["user_id"] == 7, payload
    assert payload["action_data"]["chemical"] == "Spinosad", payload
    assert payload["action_data"]["intervention"] == "urgent_spray", payload
    assert payload["farm_context"]["cash_reserve_usd"] == 900.0, payload


@pytest.mark.parametrize(
    "status_code,body,expected",
    [
        (200, {"allowed": False, "arabic_explanation": "مادّة محظورة"}, gate.DENIED),
        (200, {"allowed": False, "requires_human_approval": True}, gate.DENIED),
        (200, {"allowed": "true"}, gate.DENIED),
        (200, {"allowed": 1}, gate.DENIED),
        (200, {"allowed": True, "evaluation_only": True}, gate.DENIED),
        (200, {}, gate.DENIED),
        (200, [True], gate.ERROR),
        (200, "not json", gate.ERROR),
        (401, {"detail": "invalid token"}, gate.UNAUTHORIZED),
        (403, {"detail": "forbidden"}, gate.UNAUTHORIZED),
        (422, {"detail": "Missing or invalid guardrails evidence"}, gate.CONTRACT_REJECTED),
        (500, {"detail": "boom"}, gate.ERROR),
        (503, {"detail": "not ready"}, gate.ERROR),
    ],
)
def test_every_non_allow_response_blocks(status_code, body, expected):
    transport, calls = _transport(status_code, body)
    verdict = _evaluate(transport)
    assert len(calls) == 1, "the engine must have been asked"
    assert verdict["allowed"] is False, f"{status_code} {body!r} must block: {verdict}"
    assert verdict["status"] == expected, verdict
    assert gate.is_execution_allowed(verdict) is False, verdict


@pytest.mark.parametrize(
    "exc,expected",
    [
        (httpx.ReadTimeout("slow"), gate.TIMEOUT),
        (httpx.ConnectTimeout("slow"), gate.TIMEOUT),
        (httpx.ConnectError("refused"), gate.UNREACHABLE),
        (RuntimeError("unexpected"), gate.ERROR),
    ],
)
def test_transport_failures_block(exc, expected):
    transport, _ = _transport(raise_exc=exc)
    verdict = _evaluate(transport)
    assert verdict["allowed"] is False, verdict
    assert verdict["status"] == expected, verdict


def test_missing_service_token_blocks_without_calling(monkeypatch):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "  ")
    transport, calls = _transport(200, {"allowed": True})
    verdict = _evaluate(transport)
    assert verdict["status"] == gate.SERVICE_TOKEN_MISSING, verdict
    assert verdict["allowed"] is False, verdict
    assert calls == [], "no unauthenticated call may be sent"


def test_today_flow_context_has_no_pesticide_evidence_so_blocks_without_calling():
    # تدفّق الآفة اليوم لا يحمل مادّة/جرعة/اقتصاداً ولا يوجد منشئ W1-12 ⇒ evidence_unavailable.
    transport, calls = _transport(200, {"allowed": True})
    ctx = {"approval_status": "approved", "action_type": "urgent_spray", "severity": 0.9}
    verdict = _evaluate(transport, ctx=ctx, farm_fn=None)
    assert verdict["status"] == gate.EVIDENCE_UNAVAILABLE, verdict
    assert verdict["allowed"] is False, verdict
    assert "action_data.chemical" in verdict["missing_fields"], verdict
    assert "farm_context.cash_reserve_usd" in verdict["missing_fields"], verdict
    assert calls == [], "a request the contract rejects must not be sent"


def test_evidence_with_no_server_source_is_named_in_the_verdict():
    """W1-12 review (declared limitation): the treatment and the cash reserve have no server
    source, so the gate cannot allow; the verdict says so instead of only "missing"."""
    transport, calls = _transport(200, {"allowed": True})
    farm = {"annual_revenue_usd": 900.0, "annual_costs_usd": 400.0}
    verdict = _evaluate(transport, ctx={"field_id": "f1"}, farm_fn=lambda t, f: farm)
    assert verdict["status"] == gate.EVIDENCE_UNAVAILABLE, verdict
    assert verdict["allowed"] is False, verdict
    assert verdict["no_server_source"] == [
        "action_data.chemical",
        "action_data.dosage_kg_ha",
        "action_data.cost_usd",
        "action_data.projected_revenue_increase_usd",
        "farm_context.cash_reserve_usd",
    ], f"keys no server record can fill are named: {verdict}"
    assert "farm_context.annual_costs_usd" not in verdict["no_server_source"], verdict
    assert calls == [], "a request the contract rejects must not be sent"


@pytest.mark.parametrize("user_id", ["u-uuid-like", "0", "-3", "", None, True])
def test_non_numeric_identity_blocks(user_id):
    transport, calls = _transport(200, {"allowed": True})
    verdict = _evaluate(transport, user_id=user_id)
    assert verdict["status"] == gate.IDENTITY_UNAVAILABLE, verdict
    assert verdict["allowed"] is False, verdict
    assert calls == [], "no call without a valid users.id"


def test_farm_context_provider_error_blocks():
    def _boom(tenant_id, field_id):
        raise RuntimeError("db down")

    transport, calls = _transport(200, {"allowed": True})
    verdict = _evaluate(transport, farm_fn=_boom)
    assert verdict["status"] == gate.ERROR, verdict
    assert verdict["allowed"] is False, verdict
    assert calls == [], "no call when evidence could not be read"


# ── التكامل مع خطوة التنفيذ في التدفّق ──


def _execute_step(**kwargs):
    return {s.step_id: s for s in build_pest_escalation_steps(**kwargs)}["execute"].fn


def test_execute_step_blocks_when_no_gate_is_wired():
    called: list[int] = []
    execute = _execute_step(execute_fn=lambda ctx: called.append(1) or {"executed": True})
    res = execute({"approval_status": "approved", "action_type": "urgent_spray"})
    assert res["executed"] is False, res
    assert res["blocked_by"] == "guardrails", res
    assert res["guardrails"]["status"] == "gate_not_configured", res
    assert called == [], "no spray without a safety gate"


@pytest.mark.parametrize(
    "gate_fn",
    [
        lambda ctx: {"allowed": False, "status": "denied"},
        lambda ctx: {"allowed": "yes"},
        lambda ctx: None,
        lambda ctx: (_ for _ in ()).throw(RuntimeError("gate crashed")),
    ],
    ids=["deny", "truthy", "none", "raises"],
)
def test_execute_step_blocks_on_any_non_allow_gate(gate_fn):
    called: list[int] = []
    execute = _execute_step(
        execute_fn=lambda ctx: called.append(1) or {"executed": True}, safety_gate_fn=gate_fn
    )
    res = execute({"approval_status": "approved", "action_type": "urgent_spray"})
    assert res["executed"] is False, res
    assert res["blocked_by"] == "guardrails", res
    assert called == [], "execute_fn must not run when the gate did not allow"


def test_gate_not_consulted_before_expert_approval():
    asked: list[int] = []
    execute = _execute_step(safety_gate_fn=lambda ctx: asked.append(1) or {"allowed": True})
    res = execute({"approval_status": "pending", "action_type": "urgent_spray"})
    assert res["executed"] is False, res
    assert asked == [], "the safety gate runs after approval, not instead of it"


def test_flow_end_to_end_with_real_gate_denied_by_engine():
    # التدفّق كاملاً مع البوّابة الحقيقيّة: أدلّة كاملة والمحرّك يرفض ⇒ لا رشّ ولا متابعة.
    transport, calls = _transport(200, {"allowed": False, "arabic_explanation": "محظور"})
    sprayed: list[int] = []
    store = InMemoryWorkflowStore()
    evidence = {k: v for k, v in _EVIDENCE_CTX.items() if k != "approval_status"}

    def _gate(ctx):
        return gate.evaluate_pesticide_guardrails(
            ctx, tenant_id=TENANT, user_id="7", farm_context_fn=_farm_fn, transport=transport
        )

    def _spray(ctx):
        sprayed.append(1)
        return {"executed": True, "execution_ref": "x"}

    run_pest_escalation("gw1", store=store, initial_context=evidence, execute_fn=_spray)
    st = run_pest_escalation(
        "gw1",
        store=store,
        initial_context={"approval_status": "approved"},
        execute_fn=_spray,
        safety_gate_fn=_gate,
    )
    assert st.status == WorkflowStatus.COMPLETED, st.status
    assert len(calls) == 1, "engine consulted once on execute"
    assert sprayed == [], "denied by guardrails must not spray"
    assert st.step_results["execute"]["guardrails"]["status"] == gate.DENIED, st.step_results
    assert st.step_results["follow_up"]["follow_up_scheduled"] is False, st.step_results


def test_flow_end_to_end_with_real_gate_allowed_by_engine():
    transport, calls = _transport(200, {"allowed": True, "overall_risk": "LOW"})
    sprayed: list[int] = []
    store = InMemoryWorkflowStore()
    evidence = {k: v for k, v in _EVIDENCE_CTX.items() if k != "approval_status"}

    def _gate(ctx):
        return gate.evaluate_pesticide_guardrails(
            ctx, tenant_id=TENANT, user_id=7, farm_context_fn=_farm_fn, transport=transport
        )

    def _spray(ctx):
        sprayed.append(1)
        return {"executed": True, "execution_ref": "x"}

    run_pest_escalation("gw2", store=store, initial_context=evidence, execute_fn=_spray)
    st = run_pest_escalation(
        "gw2",
        store=store,
        initial_context={"approval_status": "approved"},
        execute_fn=_spray,
        safety_gate_fn=_gate,
    )
    assert sprayed == [1], "allowed by guardrails after approval sprays once"
    assert st.step_results["execute"]["guardrails"]["status"] == gate.ALLOWED, st.step_results
    assert len(calls) == 1, "engine consulted once"
