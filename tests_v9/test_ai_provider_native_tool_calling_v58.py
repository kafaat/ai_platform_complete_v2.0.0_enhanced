"""حارس V58 — Provider-native tool calling.

يفرض أن المزوّد يرى JSON Schema للأدوات المسموحة فقط، وأن ردود tool_use/provider
تُترجم إلى عقد SAHOOL الداخلي، ثم تُنفّذ عبر Harness لا مباشرةً.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import ai_generation as G  # noqa: E402


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _Client:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, endpoint, headers=None, json=None):
        self.__class__.calls.append(json)
        if len(self.__class__.calls) == 1:
            return _Resp(
                {
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "tc-1",
                                        "type": "function",
                                        "function": {
                                            "name": "get_truecolor_scene",
                                            "arguments": '{"field_id":"field-1","date":"2026-06-01"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            )
        return _Resp(
            {"choices": [{"message": {"content": "الجواب النهائي بعد قراءة أداة TrueColor."}}]}
        )


def test_provider_tool_schema_is_native_and_capability_filtered():
    cfg = G.GenConfig("openrouter", "https://example.test", {}, "m", "openai_chat")
    tools = G._provider_tools(cfg, ["can_read_field_data", "can_read_historical_imagery"])
    names = [t["function"]["name"] for t in tools]
    assert "get_truecolor_scene" in names
    assert "request_imagery_backfill" not in names
    assert all(t["type"] == "function" for t in tools)

    anthropic = G.GenConfig("anthropic", "https://example.test", {}, "m", "messages")
    a_tools = G._provider_tools(anthropic, ["can_read_field_data"])
    assert all("input_schema" in t for t in a_tools)
    assert "get_weather_history" in [t["name"] for t in a_tools]


def test_extracts_openai_and_anthropic_tool_calls():
    cfg = G.GenConfig("openrouter", "u", {}, "m", "openai_chat")
    calls = G._extract_provider_tool_calls(
        cfg,
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "1",
                                "function": {
                                    "name": "get_field_state",
                                    "arguments": '{"field_id":"f"}',
                                },
                            }
                        ]
                    }
                }
            ]
        },
    )
    assert calls == [{"id": "1", "tool": "get_field_state", "params": {"field_id": "f"}}]

    acfg = G.GenConfig("anthropic", "u", {}, "m", "messages")
    acalls = G._extract_provider_tool_calls(
        acfg,
        {
            "content": [
                {"type": "tool_use", "id": "a1", "name": "get_alerts", "input": {"field_id": "f"}}
            ]
        },
    )
    assert acalls[0]["tool"] == "get_alerts"


@pytest.mark.asyncio
async def test_generate_executes_provider_native_tool_and_second_pass(monkeypatch):
    monkeypatch.setenv("AI_GENERATION_ENABLED", "1")
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("AI_MODEL", "deepseek/deepseek-chat")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    _Client.calls = []
    monkeypatch.setattr(G.httpx, "AsyncClient", _Client)

    def fetcher(name, params):
        return {"scene": "truecolor", "field_id": params.get("field_id")}

    gen = await G.generate(
        "ما حالة صورة الحقل؟",
        "context",
        policy={"data_sharing_level": "redacted_external"},
        allowed_capabilities=["can_read_field_data", "can_read_historical_imagery"],
        tool_fetcher=fetcher,
        tenant_id="tenant-1",
        timestamp="2026-07-01T00:00:00Z",
    )
    assert gen is not None
    assert gen.text == "الجواب النهائي بعد قراءة أداة TrueColor."
    assert gen.tool_rounds == 1
    assert gen.tool_calls[0]["tool"] == "get_truecolor_scene"
    assert gen.tool_calls[0]["outcome"] == "executed"
    assert len(_Client.calls) == 2
    assert "tools" in _Client.calls[0]
    assert "نتائج أدوات" in _Client.calls[1]["messages"][1]["content"]


def test_main_merges_provider_and_manual_tool_calls_static():
    # P0 decomposition: provider/manual tool merging moved into ai_evidence_runtime.py.
    source = (ROOT / "services/ai_agronomist/main.py").read_text(encoding="utf-8") + (
        ROOT / "services/ai_agronomist/ai_evidence_runtime.py"
    ).read_text(encoding="utf-8")
    assert 'allowed_capabilities=_policy_for_generation.get("allowed_capabilities")' in source
    assert "tool_fetcher=_build_agent_tool_fetcher" in source
    assert "provider_tool_calls" in source
    assert "all_tool_calls = list(provider_tool_calls)" in source
    assert '"provider_tool_rounds": provider_tool_rounds' in source
