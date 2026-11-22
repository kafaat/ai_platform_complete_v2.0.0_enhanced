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
        assert calls[0][1]["context"] == {
            "_platform_bearer": "verified-caller",
            # No field: nothing is server-bound, and the record says so (W2-17).
            "_facts_provenance": {
                "trusted_path": False,
                "crop_source": None,
                "weather_source": None,
                "request_supplied_keys": [],
            },
        }


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


def test_optimize_degrades_instead_of_inventing_scenarios_without_crop_simulation(monkeypatch):
    """_generate_scenarios يملأ الغائب بـyield=2000/water=400؛ محاكاة غير متاحة ⇒ degraded."""
    from fastapi.testclient import TestClient

    class Unavailable:
        async def execute(self, **kwargs):
            return {"type": "unavailable", "structured": {"reason": "crop_model_weather_required"}}

    class Other:
        async def execute(self, **kwargs):
            return {"type": "ok"}

    def never(*args, **kwargs):
        raise AssertionError("scenarios generated from an unavailable crop simulation")

    monkeypatch.setitem(main.skill_libraries, "crop_model", Unavailable())
    monkeypatch.setitem(main.skill_libraries, "remote_sensing", Other())
    monkeypatch.setitem(main.skill_libraries, "market", Other())
    monkeypatch.setattr(main, "_generate_scenarios", never)
    main.app.dependency_overrides[main._get_current_user] = lambda: {
        "sub": "42",
        "tenant_id": "trusted-tenant",
        "_mcp_bearer": "verified-caller",
    }
    try:
        response = TestClient(main.app).post(
            "/v1/agent/optimize",
            json={
                "query": "حسّن الحقل",
                "field_id": "field-1",
                "user_id": "forged",
                "tenant_id": "forged",
            },
        )
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["structured_data"] == {
        "status": "degraded",
        "reason": "crop_model_weather_required",
        "domain": "optimization",
    }
    assert body["confidence"] == 0.0


def test_mcp_caller_errors_do_not_open_the_shared_breaker(monkeypatch):
    """A tool's isError reply (bad caller arguments) must not trip the breaker for all tenants."""
    import circuit_breaker
    import pytest
    from mcp_client import MCPProtocolError, MCPToolError

    registry = circuit_breaker.CircuitBreakerRegistry(
        failure_threshold=5, recovery_timeout=30.0, success_threshold=2
    )
    monkeypatch.setattr(circuit_breaker, "mcp_breakers", registry)
    replies = []

    def handler(request):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    client = MCPClient({"market": "http://market.invalid"})

    async def scenario():
        client._clients["market"] = httpx.AsyncClient(
            base_url="http://market.invalid", transport=httpx.MockTransport(handler)
        )
        breaker = registry.get("market")
        with client.bind_credentials("verified", "tenant-a"):
            for _ in range(6):
                replies.append(
                    httpx.Response(200, json={"isError": True, "content": [{"text": "bad"}]})
                )
                with pytest.raises(MCPToolError):
                    await client.call_tool("market", "get_market_price", {"crop": "x"})
            for _ in range(6):
                replies.append(httpx.Response(200, content=b"not json"))
                with pytest.raises(MCPProtocolError):
                    await client.call_tool("market", "get_market_price", {"crop": "x"})
            assert breaker.state == circuit_breaker.CircuitState.CLOSED
            assert breaker.status()["failures"] == 0
            # Transport failures still open it.
            for _ in range(5):
                replies.append(httpx.ConnectError("down"))
                with pytest.raises(httpx.ConnectError):
                    await client.call_tool("market", "get_market_price", {"crop": "x"})
            assert breaker.state == circuit_breaker.CircuitState.OPEN
            # A caller error during the half-open probe frees the probe slot.
            breaker._opened_at -= 31.0
            replies.append(httpx.Response(200, json={"isError": True, "content": [{"text": "b"}]}))
            with pytest.raises(MCPToolError):
                await client.call_tool("market", "get_market_price", {"crop": "x"})
            replies.append(httpx.Response(200, json={"content": [{"text": "{}"}]}))
            await client.call_tool("market", "get_market_price", {"crop": "x"})
        await client.close()

    _run(scenario())


def test_market_context_values_must_be_strings():
    from skills.market_skill import MarketSkill

    class NoCall:
        async def call_tool(self, *args, **kwargs):
            raise AssertionError("non-string context reached the market tool")

    skill = MarketSkill(NoCall())
    for context, reason in (
        ({"crop": {"$ne": ""}, "market": "sanaa"}, "crop_required"),
        ({"crop": ["wheat"], "market": "sanaa"}, "crop_required"),
        ({"crop": 7, "market": "sanaa"}, "crop_required"),
        ({"crop": "   ", "market": "sanaa"}, "crop_required"),
        ({"crop": "wheat", "market": {"$gt": ""}}, "market_required"),
        ({"crop": "wheat", "market": 3}, "market_required"),
    ):
        result = _run(skill.execute("price_current", context=context))
        assert result["type"] == "unavailable"
        assert result["structured"]["reason"] == reason


def _optimize_http(monkeypatch, skills, body=None, governance=None):
    from fastapi.testclient import TestClient

    calls = []

    class Recorder:
        def __init__(self, name, result):
            self.name, self.result = name, result

        async def execute(self, **kwargs):
            calls.append((self.name, kwargs))
            return self.result

    for name, result in skills.items():
        monkeypatch.setitem(main.skill_libraries, name, Recorder(name, result))

    async def field_state(client, field_id, tenant_id):
        calls.append(("field_state", (field_id, tenant_id)))
        return {"validity": "valid", "inputs": {"weather_age_hours": 2}}

    async def validate(*args, **kwargs):
        calls.append(("governance", args))
        return governance or {"allowed": False}

    async def server_facts(client, field_id, tenant_id, *, needs=None):
        calls.append(("server_facts", (field_id, tenant_id)))
        assert needs == frozenset({"season", "weather"}), f"optimize needs every fact: {needs}"
        return {"crop": "barley", "planting_date": "2026-10-01"}, {
            "season": {"status": "bound", "season_id": "s-1"},
            "weather": {"status": "unavailable", "reason": "season_weather_not_yet_archived"},
        }

    monkeypatch.setattr(main, "_fetch_field_state", field_state)
    monkeypatch.setattr(main, "_resolve_server_facts", server_facts)
    monkeypatch.setattr(main, "_validate_via_guardrails", validate)
    main.app.dependency_overrides[main._get_current_user] = lambda: {
        "sub": "42",
        "tenant_id": "trusted-tenant",
        "_mcp_bearer": "verified-caller",
    }
    try:
        response = TestClient(main.app).post(
            "/v1/agent/optimize",
            json=body
            or {
                "query": "حسّن الحقل",
                "field_id": "field-1",
                "user_id": "forged",
                "tenant_id": "forged",
                "context": {"crop": "wheat", "_platform_bearer": "forged"},
            },
        )
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    return response.json(), calls


def test_optimize_binds_field_state_context_and_bearer_like_query(monkeypatch):
    unavailable = {"type": "unavailable", "structured": {"reason": "x"}}
    _, calls = _optimize_http(
        monkeypatch,
        {"remote_sensing": unavailable, "crop_model": unavailable, "market": unavailable},
    )
    assert ("field_state", ("field-1", "trusted-tenant")) in calls
    assert ("server_facts", ("field-1", "trusted-tenant")) in calls
    skill_calls = {name: kwargs for name, kwargs in calls if name in main.skill_libraries}
    assert set(skill_calls) == {"remote_sensing", "crop_model", "market"}
    for kwargs in skill_calls.values():
        context = kwargs["context"]
        # W2-17: the season's crop, not the body's "wheat".
        assert context["crop"] == "barley", context
        assert context["_facts_provenance"]["ignored_request_keys"] == ["crop"], context
        assert context["field_state"]["validity"] == "valid"
        assert context["_platform_bearer"] == "verified-caller"
        assert kwargs["tenant_id"] == "trusted-tenant"
        assert kwargs["user_id"] == "42"


def test_optimize_without_observed_price_degrades_instead_of_pricing_a_constant(monkeypatch):
    simulation = {"type": "crop_simulation", "yield_kg_ha": 3000.0, "total_water_mm": 350.0}
    for market in (
        {"type": "unavailable", "structured": {"reason": "market_observations_unavailable"}},
        {"type": "price_history", "structured": {"current_price_usd": 17.5}},
        {"type": "price_history", "price_yer_kg": True},
        {"type": "price_history", "price_yer_kg": float("nan")},
        {"type": "price_history", "price_yer_kg": 0},
    ):
        body, calls = _optimize_http(
            monkeypatch,
            {"remote_sensing": {"type": "ok"}, "crop_model": simulation, "market": market},
        )
        assert body["structured_data"] == {
            "status": "degraded",
            "reason": "market_price_unavailable",
            "domain": "optimization",
        }
        assert "governance" not in [name for name, _ in calls]
    assert main._generate_scenarios({}, simulation, {}) == []
    # airuntime-6: an observed price alone no longer prices scenarios with invented unit costs.
    market = {"price_yer_kg": 250.0}
    assert main._generate_scenarios({}, simulation, market) == [], "priced without agriai costs"
    uncosted = {"status": "insufficient", "missing_inputs": ["costs"]}
    assert main._generate_scenarios({}, simulation, market, uncosted) == []
    costed = {
        "status": "costed",
        "source": "agriai-engine /v1/plan",
        "best": {"name": "wheat", "price_per_kg": 250.0, "total_cost": 90000.0},
    }
    priced = main._generate_scenarios({}, simulation, market, costed)
    assert len(priced) == 25, priced
    neutral = next(s for s in priced if s["irrigation_mult"] == 1.0 and s["fertilizer_mult"] == 1.0)
    assert neutral["profit_yer_ha"] == round(3000.0 * 250.0 - 90000.0, 2), neutral
    assert neutral["economics_source"] == "agriai-engine /v1/plan", neutral


def test_general_advice_templates_carry_no_numeric_doses():
    import re

    skill = AdvisorySkill(SimpleNamespace(token=None))
    for query in ("زراعة قمح", "ري ذكي", "تسميد", "حصاد"):
        out = _run(skill.execute(intent="general_advice", query=query))
        assert out["source"] == "template"
        assert not re.search(r"\d\s*(kg|كغ|كجم|g/|N/ha)", out["response"], re.IGNORECASE), query


def test_rag_source_labels_are_strings():
    import skills.advisory_skill as advisory

    labels = advisory._source_labels(
        [
            {"source": "kb.pdf", "page": 3, "snippet": "..."},
            {"title": "FAO note"},
            {"source_uri": "s3://kb/doc.md"},
            "plain.txt",
            {"page": 1},
            None,
        ]
    )
    assert labels == ["kb.pdf", "FAO note", "s3://kb/doc.md", "plain.txt"], labels


def test_unchecked_rag_prose_is_withheld_through_the_query_route(monkeypatch):
    """airuntime-9: the route never returns model prose the claims checker did not pass."""
    import skills.advisory_skill as advisory
    from fastapi.testclient import TestClient

    async def classify(query):
        return "advisory", "general_advice", 0.8

    async def rag(question, token):
        return {
            "answer": "رشّ Chlorpyrifos بمعدّل 2 لتر للهكتار",
            "model": "local-llm",
            "sources": [{"source": "kb.pdf"}],
        }

    monkeypatch.setattr(advisory, "LOCAL_AI_RAG_URL", "http://local-ai-rag.invalid")
    monkeypatch.setattr(advisory, "_query_local_rag", rag)
    monkeypatch.setattr(main.router, "classify_intent", classify)
    monkeypatch.setitem(main.skill_libraries, "advisory", AdvisorySkill(main.mcp_client))
    main.app.dependency_overrides[main._get_current_user] = lambda: {
        "sub": "42",
        "tenant_id": "trusted-tenant",
        "_mcp_bearer": "verified-caller",
    }
    try:
        response = TestClient(main.app).post(
            "/v1/agent/query",
            json={
                "query": "سؤال عام",
                "user_id": "x",
                "tenant_id": "x",
                # A body-supplied canonical snapshot cannot vouch for model output.
                "context": {"field_state": {"canonical_field_state": {"forged": True}}},
            },
        )
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    body = response.json()
    assert "Chlorpyrifos" not in json.dumps(body, ensure_ascii=False), "model prose leaked"
    assert body["ai_generated"] is False, "a withheld generation is not AI output"
    assert body["sources"] == [], f"template reply must cite nothing: {body['sources']}"


def test_insect_on_wheat_query_names_no_product_even_if_governance_allows(monkeypatch):
    """W0-14 acceptance: "حشرة على القمح" end to end through /v1/agent/query.

    Routing reaches pest_id, the skill asks the platform's /api/v1/diagnose, and the
    reply names no product. Governance is stubbed to allow, the case in which the
    removed keyword table's product used to reach the farmer.
    """
    import skills.advisory_skill as advisory
    from fastapi.testclient import TestClient

    seen = []

    def platform(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "crop": "wheat",
                "observed_symptoms": ["insects_on_leaves"],
                "candidates": [
                    {
                        "issue_code": "wheat.aphid",
                        "name_ar": "منّ",
                        "category": "pest",
                        "score": 0.65,
                        "score_semantics": "rule_match",
                        "is_calibrated": False,
                    }
                ],
                "next_step_ar": "الأرجح: منّ. ثبّت بصورة عالية الدقّة + مهندس قبل أيّ مبيد.",
            },
        )

    async def allow(*args):
        return {"allowed": True, "status": "validated"}

    factory = httpx.AsyncClient
    monkeypatch.setattr(
        advisory.httpx,
        "AsyncClient",
        lambda **kw: factory(transport=httpx.MockTransport(platform), **kw),
    )
    monkeypatch.setattr(main, "_validate_actions_via_guardrails", allow)
    monkeypatch.setitem(main.skill_libraries, "advisory", AdvisorySkill(main.mcp_client))
    main.app.dependency_overrides[main._get_current_user] = lambda: {
        "sub": "42",
        "tenant_id": "trusted-tenant",
        "_mcp_bearer": "verified-caller",
    }
    try:
        response = TestClient(main.app).post(
            "/v1/agent/query",
            json={"query": "حشرة على القمح", "user_id": "x", "tenant_id": "x"},
        )
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    body = response.json()
    text = json.dumps(body, ensure_ascii=False).lower()
    for product in ("imidacloprid", "chlorpyrifos", "abamectin", "mancozeb", "metalaxyl"):
        assert product not in text, f"reply names {product}"
    assert len(seen) == 1, f"expected one diagnose call, saw {len(seen)}"
    assert seen[0].url.path == "/api/v1/diagnose", seen[0].url.path
    assert seen[0].headers["Authorization"] == "Bearer verified-caller", "bearer not forwarded"
    assert json.loads(seen[0].content)["symptoms"] == ["insects_on_leaves"], seen[0].content
    assert "منّ" in body["response_ar"], body["response_ar"]
    assert body["governance"] is None, "an informational diagnosis is not an action to govern"


def test_field_state_fetch_cannot_traverse_platform_paths(monkeypatch):
    monkeypatch.setenv("PLATFORM_TENANT_ASSERTION_KEY", "k" * 32)
    seen = []

    def handler(request):
        seen.append(request.url.raw_path)
        return httpx.Response(404)

    async def fetch():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await main._fetch_field_state(client, "../../admin/users?x=1#", "tenant-a")

    _run(fetch())
    assert len(seen) == 1
    path = seen[0].split(b"?")[0]
    assert path == b"/internal/fields/..%2F..%2Fadmin%2Fusers%3Fx%3D1%23/state"


def test_tool_catalog_marks_bootstrap_examples_unavailable_and_invoke_refuses_them():
    """S-07: the catalog must not present example contracts as live tools, and the shared
    registry must refuse them before the (example) implementation runs — even for a caller
    holding the actuator capability."""
    from fastapi.testclient import TestClient

    main.app.dependency_overrides[main._get_current_user] = lambda: {
        "sub": "42",
        "tenant_id": "trusted-tenant",
    }
    try:
        response = TestClient(main.app).get("/v1/agent/tools")
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    body = response.json()
    by_id = {t["tool_id"]: t for t in body["tools"]}
    for tool_id in ("weather.forecast", "actuator.pump.start", "ndvi.read_observation"):
        assert by_id[tool_id]["example_only"] is True
        assert by_id[tool_id]["available"] is False
    assert body["available_total"] == 0

    result = _run(
        main._tool_registry.invoke(
            "actuator.pump.start",
            {"well_id": "w1", "duration_min": 30},
            {"actuator.pump.control"},
            tenant_id="trusted-tenant",
        )
    )
    assert result.success is False and result.output is None
    assert "example-only" in result.error


# ── W2-17: server-side season, weather and economics on the trusted path ─────────────────

_W217_KEY = "w2-17-platform-assertion-key-0123456789"
_FORGED_WEATHER = {"gdd": 9999.0, "total_rain_mm": 5000.0}


def _w217_view(start, days, *, drop_tmax_on=None):
    from datetime import timedelta

    out = []
    for i in range(days):
        day = {
            "date": (start + timedelta(days=i)).isoformat(),
            "temp_max_c": 24.0,
            "temp_min_c": 8.0,
            "precipitation_mm": 1.5,
            "et0_mm": 3.1,
        }
        if drop_tmax_on == i:
            day["temp_max_c"] = None
        out.append(day)
    return {
        "days": out,
        "derived_from": "canonical_weather_state",
        "canonical_state_id": "cws-w217",
        "source_snapshot_id": "snap-w217",
        "quality_status": "validated",
        "coverage": {"missing_days": 0, "coverage_ratio": 1.0},
    }


def _w217_http(monkeypatch, *, weather_view=None, weather_status=200, agriai=None):
    """Route every outbound httpx call of the supervisor to in-process fakes and record them."""
    from datetime import date, timedelta

    import server_facts

    monkeypatch.setenv("PLATFORM_TENANT_ASSERTION_KEY", _W217_KEY)
    sowing = date.today() - timedelta(days=40)
    expected_end = date.today() - timedelta(days=server_facts.ARCHIVE_LAG_DAYS)
    seen = {"platform": [], "weather": [], "agriai": []}
    pack = {
        "field_profile": {"field_id": "field-1", "lat": 15.35, "lon": 44.2},
        "active_season": {
            "season_id": "season-7",
            "crops": ["wheat"],
            "cultivar": "Bohoth-13",
            "sowing_date": sowing.isoformat(),
            "seed_rate_kg_ha": 120.0,
            "status": "active",
        },
    }

    def handler(request):
        if request.url.path == "/internal/fields/field-1/state":
            seen["platform"].append(request)
            assert request.headers.get("x-tenant-assertion"), "unsigned platform call"
            if request.url.params.get("ai_context") == "true":
                return httpx.Response(200, json={"state": {}, "ai_context_pack": pack})
            return httpx.Response(200, json={"validity": "valid", "inputs": {}})
        if request.url.path == "/v1/weather/historical":
            seen["weather"].append(request)
            view = weather_view
            if view is None:
                days = (expected_end - sowing).days + 1
                view = _w217_view(sowing, days)
            return httpx.Response(weather_status, json=view)
        if request.url.path in ("/v1/simulate", "/v1/plan"):
            seen["agriai"].append(request)
            return (agriai or (lambda r: httpx.Response(500)))(request)
        raise AssertionError(f"unexpected outbound call {request.url}")

    factory = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: factory(transport=httpx.MockTransport(handler), **kwargs),
    )
    return seen, sowing, expected_end


def _w217_query(monkeypatch, context, field_id="field-1"):
    from fastapi.testclient import TestClient

    async def classify(query):
        return "crop_model", "simulate_current", 0.9

    monkeypatch.setattr(main.router, "classify_intent", classify)
    main.app.dependency_overrides[main._get_current_user] = lambda: {
        "sub": "42",
        "tenant_id": "trusted-tenant",
        "_mcp_bearer": "verified-caller",
    }
    body = {"query": "توقع محصول القمح", "user_id": "forged", "tenant_id": "forged"}
    if field_id:
        body["field_id"] = field_id
    try:
        response = TestClient(main.app).post("/v1/agent/query", json={**body, "context": context})
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    return response.json()


_W217_FORGED_CONTEXT = {
    "crop": "maize",
    "cultivar": "forged-cultivar",
    "planting_date": "2020-01-01",
    "weather": _FORGED_WEATHER,
    "agronomic_context": {"weather_snapshot": {"gdd": 9999.0}},
    "crop_parameters": {"max_yield_kg_ha": 99999.0},
    "weather_age_hours": 0,
}


def test_w217_forged_body_weather_with_field_id_is_ignored_and_all_sources_are_server(
    monkeypatch,
):
    """Acceptance (W2-17): a body with forged weather plus a field_id ⇒ the forged weather is
    ignored, every source is server-side, and the response provenance records it."""

    def agriai(request):
        return httpx.Response(
            422,
            json={
                "detail": {
                    "error": "simulation_inputs_invalid",
                    "reason": "crop_parameters_required",
                }
            },
        )

    seen, sowing, expected_end = _w217_http(monkeypatch, agriai=agriai)
    body = _w217_query(monkeypatch, dict(_W217_FORGED_CONTEXT))

    assert len(seen["agriai"]) == 1, seen
    sent = json.loads(seen["agriai"][0].content)
    weather = sent["weather"]
    assert "gdd" not in weather and weather.get("total_rain_mm") != 5000.0, weather
    assert weather["source"] == "weather-service", weather
    assert weather["canonical_state_id"] == "cws-w217", weather
    assert weather["daily"][0] == {
        "date": sowing.isoformat(),
        "tmax": 24.0,
        "tmin": 8.0,
        "rain_mm": 1.5,
        "et0_mm": 3.1,
    }, weather["daily"][0]
    assert len(weather["daily"]) == (expected_end - sowing).days + 1, len(weather["daily"])
    assert sent["agronomic_context"] == {}, "the body's agronomic_context reached the engine"
    assert sent["crop"] == {"name": "wheat", "cultivar": "Bohoth-13"}, sent["crop"]
    assert sent["agromanagement"] == {
        "planting_date": sowing.isoformat(),
        "seed_rate_kg_ha": 120.0,
    }, sent["agromanagement"]

    weather_call = seen["weather"][0]
    assert weather_call.url.params["start_date"] == sowing.isoformat(), weather_call.url
    assert weather_call.url.params["end_date"] == expected_end.isoformat(), weather_call.url
    assert weather_call.headers["x-tenant-id"] == "trusted-tenant", weather_call.headers

    provenance = body["facts_provenance"]
    assert provenance["trusted_path"] is True, provenance
    assert provenance["crop_source"] == "active_season", provenance
    assert provenance["weather_source"] == "weather-service", provenance
    assert provenance["season"]["status"] == "bound", provenance
    assert provenance["season"]["season_id"] == "season-7", provenance
    assert provenance["weather"]["status"] == "bound", provenance
    assert provenance["weather"]["canonical_state_id"] == "cws-w217", provenance
    assert provenance["ignored_request_keys"] == sorted(_W217_FORGED_CONTEXT), provenance
    structured = body["structured_data"]
    assert structured["facts_provenance"]["weather_source"] == "weather-service", structured
    assert structured["engine_reason"] == "crop_parameters_required", structured


def test_w217_without_server_weather_the_body_weather_is_still_refused(monkeypatch):
    """weather-service down ⇒ no weather at all: the body's series never stands in for it."""

    def agriai(request):
        raise AssertionError("simulated without server weather")

    seen, _, _ = _w217_http(monkeypatch, weather_status=502, agriai=agriai)
    body = _w217_query(monkeypatch, {"crop": "wheat", "weather": _FORGED_WEATHER})
    assert seen["agriai"] == [], "agriai was called with the body's weather"
    assert body["structured_data"]["reason"] == "crop_model_weather_required", body
    provenance = body["facts_provenance"]
    assert provenance["weather_source"] is None, provenance
    assert provenance["weather"]["reason"] == "weather_service_unavailable", provenance
    assert provenance["crop_source"] == "active_season", provenance
    detail = body["structured_data"]["facts_provenance"]
    assert detail["ignored_request_keys"] == ["crop", "weather"], detail


def test_w217_incomplete_weather_series_is_absence_not_zeros(monkeypatch):
    from datetime import date, timedelta

    import server_facts

    sowing = date.today() - timedelta(days=40)
    end = date.today() - timedelta(days=server_facts.ARCHIVE_LAG_DAYS)
    view = _w217_view(sowing, (end - sowing).days + 1, drop_tmax_on=3)

    def agriai(request):
        raise AssertionError("simulated on a series with a missing temperature")

    seen, _, _ = _w217_http(monkeypatch, weather_view=view, agriai=agriai)
    body = _w217_query(monkeypatch, {})
    assert seen["agriai"] == [], seen
    assert body["structured_data"]["reason"] == "crop_model_weather_required", body


def test_w217_without_field_the_request_is_labelled_request_body(monkeypatch):
    def agriai(request):
        return httpx.Response(422, json={"detail": {"reason": "crop_parameters_required"}})

    seen, _, _ = _w217_http(monkeypatch, agriai=agriai)
    body = _w217_query(monkeypatch, {"crop": "wheat", "weather": _FORGED_WEATHER}, field_id=None)
    assert seen["platform"] == [] and seen["weather"] == [], "a field-less request read the field"
    provenance = body["facts_provenance"]
    assert provenance == {
        "trusted_path": False,
        "crop_source": "request_body",
        "weather_source": "request_body",
        "request_supplied_keys": ["crop", "weather"],
    }, provenance


def test_w217_optimize_routes_economics_to_agriai_plan_and_degrades_when_uncosted(monkeypatch):
    """airuntime-6: the supervisor no longer prices scenarios with invented unit costs."""
    plan_requests = []

    def agriai(request):
        plan_requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "ranked": [],
                "insufficient": [
                    {"name": "wheat", "status": "insufficient", "missing_inputs": ["costs"]}
                ],
                "best": None,
            },
        )

    _w217_http(monkeypatch, agriai=agriai)
    simulation = {
        "type": "crop_simulation",
        "yield_kg_ha": 3000.0,
        "total_water_mm": 350.0,
        "sources": ["agriai-engine /v1/simulate"],
    }

    class Fixed:
        def __init__(self, result):
            self.result = result

        async def execute(self, **kwargs):
            return self.result

    monkeypatch.setitem(main.skill_libraries, "crop_model", Fixed(simulation))
    monkeypatch.setitem(main.skill_libraries, "remote_sensing", Fixed({"type": "ok"}))
    monkeypatch.setitem(main.skill_libraries, "market", Fixed({"price_yer_kg": 250.0}))

    def never(*args, **kwargs):
        raise AssertionError("scenarios generated without a costed agriai plan")

    monkeypatch.setattr(main, "_generate_scenarios", never)
    from fastapi.testclient import TestClient

    main.app.dependency_overrides[main._get_current_user] = lambda: {
        "sub": "42",
        "tenant_id": "trusted-tenant",
        "_mcp_bearer": "verified-caller",
    }
    try:
        response = TestClient(main.app).post(
            "/v1/agent/optimize",
            json={
                "query": "حسّن الحقل",
                "field_id": "field-1",
                "user_id": "forged",
                "tenant_id": "forged",
                "context": {"costs": {"seed": 1.0}, "weather": _FORGED_WEATHER},
            },
        )
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["structured_data"] == {
        "status": "degraded",
        "reason": "economics_inputs_insufficient",
        "domain": "optimization",
    }, body
    assert len(plan_requests) == 1, plan_requests
    candidate = plan_requests[0]["candidates"][0]
    assert candidate["name"] == "wheat" and candidate["price_per_kg"] == 250.0, candidate
    assert "costs" not in candidate, "the body's costs reached the economics plan"
    assert plan_requests[0]["weather"]["source"] == "weather-service", plan_requests[0]
    assert body["facts_provenance"]["ignored_request_keys"] == ["costs", "weather"], body


# ── F3 (audit L148): unsourced template numbers and the answer's stated origin ──
_UNSOURCED_FIGURE = (
    r"[0-9٠-٩]|%|٪|"
    r"يناير|فبراير|مارس|[أا]بريل|مايو|يونيو|يوليو|[أا]غسطس|سبتمبر|[أا]كتوبر|نوفمبر|ديسمبر"
)
_TEMPLATE_QUERIES = ("زراعة قمح", "ري ذكي", "تسميد", "حصاد", "سؤال لا يطابق أيّ قالب")


def test_general_advice_templates_publish_no_figure_without_a_source():
    """A fixed template cites nothing (``sources == []``), so it may state no number.

    The fallback used to say "ري عند 30% رطوبة", "يوفر 40% مياه", "3–4 مرات",
    "رطوبة الحبوب (13–14%)" and sowing/harvest months with no reviewed source behind them.
    """
    import re

    skill = AdvisorySkill(SimpleNamespace(token=None))
    for query in _TEMPLATE_QUERIES:
        out = _run(skill.execute(intent="general_advice", query=query))
        assert out["source"] == "template", out
        assert out["sources"] == [], out
        found = re.findall(_UNSOURCED_FIGURE, out["response"])
        assert not found, f"{query}: unsourced figure(s) {found} in {out['response']!r}"
        assert "مهندس" in out["response"], f"{query}: no referral to a specialist"


def _advisory_route(monkeypatch, *, rag=None, skill=None, domain="advisory", field_id=None):
    """POST /v1/agent/query with the intent classifier pinned at 0.8."""
    import skills.advisory_skill as advisory
    from fastapi.testclient import TestClient

    async def classify(query):
        return domain, "general_advice", 0.8

    monkeypatch.setattr(main.router, "classify_intent", classify)
    monkeypatch.setattr(advisory, "LOCAL_AI_RAG_URL", "http://local-ai-rag.invalid" if rag else "")
    if rag:
        monkeypatch.setattr(advisory, "_query_local_rag", rag)
    if domain == "advisory":
        monkeypatch.setitem(
            main.skill_libraries, "advisory", skill or AdvisorySkill(main.mcp_client)
        )
    main.app.dependency_overrides[main._get_current_user] = lambda: {
        "sub": "42",
        "tenant_id": "trusted-tenant",
        "_mcp_bearer": "verified-caller",
    }
    body = {"query": "ري ذكي", "user_id": "x", "tenant_id": "x"}
    if field_id:
        body["field_id"] = field_id
    try:
        response = TestClient(main.app).post("/v1/agent/query", json=body)
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    return response.json()


def _assert_uncalibrated_envelope(body):
    assert body["confidence"] == 0.0, "intent confidence reported as confidence in the answer"
    assert body["confidence_calibrated"] is False, body
    assert body["requires_human_review"] is True, body
    note = body["provenance_note_ar"]
    assert "غير مُعايَرة" in note and "مراجعة" in note, note


def test_template_answer_states_its_origin_and_not_the_intent_confidence(monkeypatch):
    body = _advisory_route(monkeypatch)
    assert body["text_source"] == "template", body
    assert body["generation_status"] == "not_attempted", body
    assert body["intent_confidence"] == 0.8, "the classifier's number is kept under its own name"
    _assert_uncalibrated_envelope(body)
    assert "قالب" in body["provenance_note_ar"], body["provenance_note_ar"]


def test_withheld_generation_is_named_in_the_route_answer(monkeypatch):
    async def rag(question, token):
        return {"answer": "رشّ 2 لتر للهكتار", "model": "local-llm", "sources": [{"source": "kb"}]}

    body = _advisory_route(monkeypatch, rag=rag)
    assert body["text_source"] == "template", body
    assert body["generation_status"] == "suppressed_unvalidated_output", body
    assert body["ai_generated"] is False
    _assert_uncalibrated_envelope(body)
    assert "حُجب" in body["provenance_note_ar"], body["provenance_note_ar"]


def test_validated_facts_and_evidence_only_answers_are_told_apart(monkeypatch):
    class _Skill:
        def __init__(self, result):
            self.result = result

        async def execute(self, **kwargs):
            return dict(self.result)

    validated = {
        "type": "general_advice",
        "response": "/weather/rain_mm: 4",
        "source": "llm-rag",
        "calibrated": False,
        "ai_generated": True,
        "generation_status": "validated_structured_facts",
        "sources": ["kb.pdf"],
    }
    body = _advisory_route(monkeypatch, skill=_Skill(validated))
    assert body["text_source"] == "validated_facts", body
    assert body["generation_status"] == "validated_structured_facts", body
    _assert_uncalibrated_envelope(body)

    # Model output that did not pass the claims checker is never called validated facts.
    body = _advisory_route(
        monkeypatch, skill=_Skill({**validated, "generation_status": "succeeded"})
    )
    assert body["text_source"] == "undeclared", body

    diagnosis = {
        "type": "diagnosis_preliminary",
        "response": "تشخيص أوّلي",
        "source": "platform-diagnose",
        "calibrated": False,
        "actionable": False,
        "generation_status": "not_attempted",
        "sources": ["SAHOOL symptom rules (/api/v1/diagnose)"],
    }
    body = _advisory_route(monkeypatch, skill=_Skill(diagnosis))
    assert body["text_source"] == "evidence_only", body
    _assert_uncalibrated_envelope(body)

    # A skill that claims calibration or its own confidence cannot raise the answer's.
    boast = {**diagnosis, "source": "somewhere", "calibrated": True, "confidence": 0.99}
    body = _advisory_route(monkeypatch, skill=_Skill(boast))
    assert body["text_source"] == "undeclared", body
    _assert_uncalibrated_envelope(body)


def test_refusal_answers_are_system_notices_with_no_confidence(monkeypatch):
    class _Unavailable:
        async def execute(self, **kwargs):
            return {"type": "unavailable", "response": "تعذّر", "source": "template", "sources": []}

    class _Down:
        async def execute(self, **kwargs):
            raise httpx.ConnectError("down")

    for skill in (_Unavailable(), _Down()):
        body = _advisory_route(monkeypatch, skill=skill)
        assert body["text_source"] == "system_notice", body
        _assert_uncalibrated_envelope(body)

    monkeypatch.delitem(main.skill_libraries, "advisory", raising=False)
    body = _advisory_route(monkeypatch, domain="no-such-domain")
    assert body["text_source"] == "system_notice", body
    assert body["intent_confidence"] is None or body["intent_confidence"] == 0.8
    _assert_uncalibrated_envelope(body)


def test_governance_withheld_answer_is_a_system_notice(monkeypatch):
    proposal = {
        "type": "irrigation_advice",
        "amount_mm": 29.8,
        "advice": "irrigate 29.8",
        "actions": ["irrigate"],
        "actionable": True,
        "source": "llm-rag",
        "generation_status": "validated_structured_facts",
        "sources": ["canonical"],
    }
    body, _calls = _query_http(
        monkeypatch, proposal, {"allowed": None, "status": "advisory_pending_validation"}
    )
    assert body["text_source"] == "system_notice", body
    assert body["generation_status"] == "not_reported", body
    assert body["intent_confidence"] == 0.9
    _assert_uncalibrated_envelope(body)
