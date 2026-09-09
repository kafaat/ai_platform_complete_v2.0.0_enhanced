#!/usr/bin/env python3
"""Offline AI/orchestration forensic tests for SAHOOL supervisor-agent.

Covers routing, MCP failover sanitisation, field-state grounding, hallucination
fallbacks, deterministic formatting, and multi-skill trace shape without live LLMs.
"""

import asyncio
import json
import os
import sys
from types import SimpleNamespace

_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
for _p in (_REPO_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import httpx  # noqa: E402
import main  # noqa: E402
from mcp_client import MCPClient, classify_mcp_error  # noqa: E402
from router import HierarchicalRouter  # noqa: E402
from skills.advisory_skill import AdvisorySkill, advisory_source  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def test_router_understands_agronomic_costly_arabic_intents():
    router = HierarchicalRouter({})
    cases = [
        ("كم احتياج الري لحقل القمح؟", "crop_model", "irrigation_advice"),
        ("توقع محصول القمح لهذا الموسم", "crop_model", "simulate_current"),
        ("ما سعر القمح في السوق؟", "market", "price_current"),
        ("اعرض مؤشر NDVI للحقل", "remote_sensing", "ndvi"),
    ]
    for query, domain, sub_intent in cases:
        d, s, c = _run(router.classify_intent(query))
        assert (d, s) == (domain, sub_intent)
        assert 0 <= c <= 1


def test_mcp_parallel_failures_are_sanitized_not_raw_exception_leaks():
    class _Client(MCPClient):
        async def call_tool(self, server_name, tool_name, arguments, request_id=None):
            if server_name == "weather":
                raise httpx.ConnectError("connect failed to http://secret.internal:8000/token")
            return {"ok": True}

    client = _Client({"weather": "http://x", "market": "http://y"}, token="t")
    result = _run(
        client.call_tools_parallel(
            [
                {"server": "weather", "tool": "get_forecast", "args": {}},
                {"server": "market", "tool": "get_price", "args": {}},
            ]
        )
    )
    failed = result[0]
    assert failed["status"] == "failed"
    assert failed["error"] == "tool_call_failed"
    assert failed["error_type"] == "network_error"
    assert "secret.internal" not in json.dumps(failed)
    assert result[1]["status"] == "success"


def test_mcp_error_classification_stable_categories():
    assert classify_mcp_error(httpx.TimeoutException("slow")) == "timeout"
    assert classify_mcp_error(httpx.ConnectError("no route")) == "network_error"
    assert classify_mcp_error(RuntimeError("boom")) == "unexpected_error"


def test_field_state_binding_is_grounded_and_does_not_overwrite_user_context():
    context = {"ndvi_mean": 0.44, "custom": "keep"}
    field_state = {
        "remote_sensing": {"available": True, "ndvi_mean": 0.18},
        "inputs": {"weather_age_hours": 3},
    }
    out = main.bind_field_context(context, field_state)
    assert out["field_state"] == field_state
    assert out["ndvi_mean"] == 0.44  # user-provided context is not overwritten
    assert out["weather_age_hours"] == 3
    assert context.get("field_state") is None  # no mutation


def test_advisory_no_rag_no_template_match_is_honest_low_capability_response(monkeypatch):
    monkeypatch.setattr("skills.advisory_skill.LOCAL_AI_RAG_URL", "")
    skill = AdvisorySkill(SimpleNamespace(token="t"))
    result = _run(skill.execute(intent="general_advice", query="كم أروي هذا الحقل دون بيانات؟"))
    assert result["source"] == "template"
    assert result["calibrated"] is False
    assert result["sources"] == []
    assert "توسيع قاعدة المعرفة" in result["response"]


def test_advisory_source_only_claims_llm_when_rag_configured_and_successful():
    assert advisory_source(None, True) == "template"
    assert advisory_source("", True) == "template"
    assert advisory_source("http://rag", False) == "template"
    assert advisory_source("http://rag", True) == "llm-rag"


def test_multi_agent_parallel_trace_preserves_per_tool_statuses():
    class _Client(MCPClient):
        async def call_tool(self, server_name, tool_name, arguments, request_id=None):
            if tool_name == "raster":
                return {"content": [{"text": "{}"}]}
            raise httpx.TimeoutException("weather timeout with http://hidden")

    client = _Client({"sentinel": "http://x", "weather": "http://y"}, token="t")
    trace = _run(
        client.call_tools_parallel(
            [
                {"server": "sentinel", "tool": "raster"},
                {"server": "weather", "tool": "forecast"},
            ]
        )
    )
    assert [item["status"] for item in trace] == ["success", "failed"]
    assert trace[1]["error_type"] == "timeout"
    assert "hidden" not in json.dumps(trace)


def test_formatting_is_deterministic_for_same_structured_result():
    result = {
        "type": "irrigation_advice",
        "advice": "ري خلال يومين",
        "amount_mm": 24.5,
        "timing": "الصباح",
    }
    first = main._format_arabic_response(result)
    second = main._format_arabic_response(dict(result))
    assert first == second
    assert "24.5" in first


# Runtime regression tests: execute real skill/router/model boundaries. These
# assertions intentionally differ from the old source-presence governance guard.
def test_irrigation_and_fertilizer_do_not_invent_missing_canonical_evidence():
    from skills.crop_model_skill import CropModelSkill

    class NoWeather:
        async def call_tool(self, *args, **kwargs):
            raise AssertionError("A weather cache warm-up is not an irrigation calculation")

    skill = CropModelSkill(NoWeather())
    for intent in ("irrigation_advice", "fertilizer_advice"):
        result = _run(skill.execute(intent=intent, context={"crop": "wheat"}))
        assert result["type"] == "unavailable"
        assert result["actionable"] is False
        assert "amount_mm" not in result
        assert "recommendation_kg_ha" not in result
        assert result["sources"] == []


def test_irrigation_consumes_canonical_owner_and_converts_observed_area(monkeypatch):
    from skills.crop_model_skill import CropModelSkill

    requests = []
    depth = [12.0]

    def handle(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer verified-caller"
        if request.url.path.endswith("irrigation-advice"):
            return httpx.Response(
                200,
                json={
                    "field_id": "field-1",
                    "recommended_mm": depth[0],
                    "timing_ar": "خلال يوم",
                    "source": "weather-service",
                },
            )
        return httpx.Response(
            200, json={"field_id": "field-1", "area_ha": 2.0, "irrigation_efficiency_pct": 80.0}
        )

    factory = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: factory(transport=httpx.MockTransport(handle), **kwargs),
    )
    skill = CropModelSkill(SimpleNamespace())
    context = {"field_state": {"validity": "valid"}, "_platform_bearer": "verified-caller"}
    dry = _run(skill.execute("irrigation_advice", field_id="field-1", context=context))
    depth[0] = 0.0
    wet = _run(skill.execute("irrigation_advice", field_id="field-1", context=context))
    assert dry["amount_mm"] == 12.0
    assert dry["structured"]["net_water_m3"] == 240.0
    assert dry["structured"]["water_m3"] == 300.0
    assert dry["structured"]["irrigation_efficiency_pct"] == 80.0
    assert wet["amount_mm"] == wet["structured"]["water_m3"] == 0.0
    assert dry["action_type"] == "irrigation" and dry["actionable"] is True
    assert {r.url.path for r in requests} == {
        "/api/v1/fields/field-1",
        "/api/v1/fields/field-1/weather/irrigation-advice",
    }


def test_irrigation_invalid_or_mismatched_canonical_payload_stays_unavailable(monkeypatch):
    from skills.crop_model_skill import CropModelSkill

    payload = [{"field_id": "another-field", "recommended_mm": 12.0}]

    def handle(request):
        body = (
            payload[0]
            if request.url.path.endswith("irrigation-advice")
            else {"field_id": "field-1", "area_ha": 2.0, "irrigation_efficiency_pct": 80.0}
        )
        return httpx.Response(200, json=body)

    factory = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: factory(transport=httpx.MockTransport(handle), **kwargs),
    )
    skill = CropModelSkill(SimpleNamespace())
    for body in (
        {"field_id": "another-field", "recommended_mm": 12.0},
        {"field_id": "field-1", "recommended_mm": -1.0},
        {"field_id": "field-1", "recommended_mm": "12.0"},
        {"field_id": "field-1"},
    ):
        payload[0] = body
        result = _run(
            skill.execute(
                "irrigation_advice",
                field_id="field-1",
                context={"field_state": {"validity": "valid"}, "_platform_bearer": "verified"},
            )
        )
        assert result["type"] == "unavailable"
        assert "amount_mm" not in result


def test_field_context_cannot_forge_server_evidence_or_credentials():
    incoming = {"field_state": {"validity": "valid"}, "_platform_bearer": "forged", "crop": "wheat"}
    assert main.bind_field_context(incoming, None) == {"crop": "wheat"}
    trusted = {"validity": "invalid"}
    result = main.bind_field_context(incoming, trusted)
    assert result["field_state"] is trusted
    assert "_platform_bearer" not in result
    assert incoming["field_state"]["validity"] == "valid"


def _query_http(monkeypatch, result, governance):
    from fastapi.testclient import TestClient

    calls = []

    class Skill:
        async def execute(self, **kwargs):
            calls.append(("skill", kwargs))
            if isinstance(result, Exception):
                raise result
            return result

    async def classify(query):
        return "crop_model", "irrigation_advice", 0.9

    async def validate(*args):
        calls.append(("governance", args))
        return governance

    monkeypatch.setattr(main.router, "classify_intent", classify)
    monkeypatch.setitem(main.skill_libraries, "crop_model", Skill())
    monkeypatch.setattr(main, "_validate_actions_via_guardrails", validate)
    main.app.dependency_overrides[main._get_current_user] = lambda: {
        "sub": "42",
        "tenant_id": "trusted-tenant",
        "_mcp_bearer": "verified-caller",
    }
    try:
        response = TestClient(main.app).post(
            "/v1/agent/query",
            json={
                "query": "متى أروي؟",
                "user_id": "forged",
                "tenant_id": "forged",
                "context": {"field_state": {"validity": "valid"}, "_platform_bearer": "forged"},
            },
        )
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    return response.json(), calls


def test_query_withholds_quantity_and_actions_until_governance_allows(monkeypatch):
    proposal = {
        "type": "irrigation_advice",
        "amount_mm": 29.8,
        "advice": "irrigate 29.8",
        "en_response": "apply 29.8 now",
        "actions": ["irrigate"],
        "action_type": "irrigation",
        "actionable": True,
        "structured": {"water_m3": 298.0},
        "sources": ["canonical"],
    }
    for governance in (
        {"allowed": None, "status": "advisory_pending_validation"},
        {"allowed": False, "status": "validated"},
        {"allowed": True, "requires_human_approval": True, "status": "validated"},
    ):
        body, calls = _query_http(monkeypatch, proposal, governance)
        assert "29.8" not in json.dumps(body)
        assert "298" not in json.dumps(body)
        assert body["response_en"] is None
        assert body["actions_triggered"] == []
        assert body["structured_data"]["status"] == "withheld"
        assert body["confidence"] == 0.0
        assert [call[0] for call in calls] == ["skill", "governance"]
        assert calls[0][1]["tenant_id"] == "trusted-tenant"
        assert calls[0][1]["user_id"] == "42"
        assert calls[0][1]["context"] == {"_platform_bearer": "verified-caller"}


def test_query_legacy_irrigation_without_actionable_flag_still_requires_governance(monkeypatch):
    body, calls = _query_http(
        monkeypatch,
        {"type": "irrigation_advice", "amount_mm": 29.8},
        {"allowed": False, "status": "invalid_action_contract"},
    )
    assert [call[0] for call in calls] == ["skill", "governance"]
    assert "29.8" not in json.dumps(body)


def test_query_validated_proposal_is_advice_and_does_not_claim_execution(monkeypatch):
    body, _ = _query_http(
        monkeypatch,
        {
            "type": "irrigation_advice",
            "amount_mm": 12.0,
            "actionable": True,
            "action_type": "irrigation",
            "structured": {"water_m3": 240.0},
            "actions": ["irrigate"],
        },
        {"allowed": True, "requires_human_approval": False, "status": "validated"},
    )
    assert "12.0" in body["response_ar"]
    assert body["structured_data"]["water_m3"] == 240.0
    assert body["actions_triggered"] == []


def test_query_dependency_failure_is_sanitized_degraded_http_response(monkeypatch):
    for exc in (httpx.ReadTimeout(""), httpx.ConnectError("http://secret-host/token")):
        body, _ = _query_http(monkeypatch, exc, {})
        assert body["structured_data"]["status"] == "degraded"
        assert body["confidence"] == 0.0
        assert "secret-host" not in json.dumps(body)
        assert body["actions_triggered"] == []


def test_actionable_missing_contract_cannot_be_reclassified_as_informational():
    result = _run(
        main._validate_actions_via_guardrails(
            {"actionable": True}, main.AgentQuery(query="q", user_id="42", tenant_id="t"), "42", "t"
        )
    )
    assert result["allowed"] is False
    assert result["status"] == "invalid_action_contract"


def test_market_tool_errors_and_empty_data_never_become_zero_prices():
    from skills.market_skill import MarketSkill

    class Tool:
        async def call_tool(self, *args, **kwargs):
            return self.envelope

    tool = Tool()
    for envelope in (
        {"isError": True, "content": [{"text": '{"error":"tool_execution_failed"}'}]},
        {"content": [{"text": "{}"}]},
        {"content": [{"text": '{"price_usd":0,"currency":"USD","sample_count":1}'}]},
        {"content": [{"text": "[]"}]},
    ):
        tool.envelope = envelope
        result = _run(
            MarketSkill(tool).execute("price_current", context={"crop": "wheat", "market": "sanaa"})
        )
        assert result["type"] == "unavailable"
        assert "price_yer_kg" not in result and "price_usd_kg" not in result
        assert result["sources"] == []


def test_market_observation_keeps_currency_and_unknown_unit_without_forecast():
    from skills.market_skill import MarketSkill

    class Tool:
        async def call_tool(self, *args, **kwargs):
            return {
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "price_usd": 17.5,
                                "currency": "USD",
                                "unit": None,
                                "sample_count": 2,
                                "updated": "2026-09-01",
                            }
                        )
                    }
                ]
            }

    result = _run(
        MarketSkill(Tool()).execute("price_current", context={"crop": "wheat", "market": "sanaa"})
    )
    assert result["structured"]["price_usd"] == 17.5
    assert result["structured"]["unit"] is None
    assert result["structured"]["forecast_available"] is False
    assert "price_yer_kg" not in result["structured"]
    assert "price_usd_kg" not in result["structured"]


def test_guardrails_missing_evidence_is_distinct_from_service_unavailability(monkeypatch):
    captured = []

    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            422, json={"detail": [{"msg": "missing financial and water context"}]}
        )

    factory = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: factory(transport=httpx.MockTransport(handle), **kwargs),
    )
    result = _run(
        main._validate_actions_via_guardrails(
            {"action_type": "irrigation", "structured": {"water_m3": 240.0}},
            main.AgentQuery(query="q", user_id="42", tenant_id="t"),
            "42",
            "t",
        )
    )
    assert result["allowed"] is False
    assert result["status"] == "context_incomplete"
    assert result["source"] == "guardrails-engine"
    assert captured[0]["action_data"] == {"water_m3": 240.0}
    assert "annual_revenue_usd" not in captured[0]["farm_context"]


def test_irrigation_requires_explicit_canonical_efficiency_for_gross_withdrawal(monkeypatch):
    from pydantic import ValidationError
    from skills.crop_model_skill import CropModelSkill, _IrrigationInputs

    observed = {}

    def handle(request):
        if request.url.path.endswith("irrigation-advice"):
            return httpx.Response(200, json={"field_id": "field-1", "recommended_mm": 12.0})
        return httpx.Response(200, json={"field_id": "field-1", "area_ha": 2.0, **observed})

    factory = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: factory(transport=httpx.MockTransport(handle), **kwargs),
    )
    skill = CropModelSkill(SimpleNamespace())
    # Neither a missing field nor invalid canonical values may be replaced by
    # a user-supplied efficiency or an implicit 100% efficiency assumption.
    for fields in (
        {},
        {"irrigation_efficiency_pct": None},
        {"irrigation_efficiency_pct": 0.0},
        {"irrigation_efficiency_pct": -1.0},
        {"irrigation_efficiency_pct": 101.0},
        {"irrigation_efficiency_pct": "80"},
        {"irrigation_efficiency_pct": True},
    ):
        observed.clear()
        observed.update(fields)
        result = _run(
            skill.execute(
                "irrigation_advice",
                field_id="field-1",
                context={
                    "field_state": {"validity": "valid"},
                    "_platform_bearer": "verified",
                    "irrigation_efficiency_pct": 100.0,
                },
            )
        )
        assert result["type"] == "unavailable"
        assert result["structured"]["reason"] == "canonical_irrigation_efficiency_required"
        assert result["actionable"] is False
        assert "water_m3" not in result["structured"]
    # JSON rejects nonfinite values before this boundary; the typed input must
    # reject them as well when invoked from internal Python call sites.
    for efficiency in (float("nan"), float("inf")):
        try:
            _IrrigationInputs(
                field_id="field-1", water_mm=12.0, area_ha=2.0, irrigation_efficiency_pct=efficiency
            )
        except ValidationError:
            pass
        else:
            raise AssertionError("Nonfinite irrigation efficiency accepted")
