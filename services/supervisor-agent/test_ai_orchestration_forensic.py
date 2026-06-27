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
