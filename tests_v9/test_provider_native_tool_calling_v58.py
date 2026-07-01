"""حراس V58 — Provider-native Tool Calling.

هذه الاختبارات تغلق الفجوة بين وجود Harness داخلي وبين تمرير تعريفات أدوات حقيقية
للمزوّد ثم تحليل ``tool_use``/``tool_calls`` وإخضاعها لحلقة الحوكمة.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import ai_generation, provider_tooling  # noqa: E402


def test_provider_tool_schemas_are_read_only_and_provider_native():
    openai_tools = provider_tooling.build_provider_tools("openai_chat")
    anthropic_tools = provider_tooling.build_provider_tools("messages")

    assert openai_tools
    assert anthropic_tools
    assert all(t["type"] == "function" for t in openai_tools)
    assert all("input_schema" in t for t in anthropic_tools)

    names = {t["function"]["name"] for t in openai_tools}
    assert "get_truecolor_scene" in names
    assert "get_weather_history" in names
    assert "request_imagery_backfill" not in names
    assert "send_recommendation" not in names


def test_extract_openrouter_openai_tool_calls():
    data = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "get_truecolor_scene",
                                "arguments": '{"field_id":"f1","date":"2026-06-01"}',
                            },
                        }
                    ]
                }
            }
        ]
    }
    calls = provider_tooling.extract_tool_calls("openai_chat", data)
    assert calls == [
        {
            "id": "call-1",
            "tool": "get_truecolor_scene",
            "params": {"field_id": "f1", "date": "2026-06-01"},
            "provider_native": True,
        }
    ]


def test_extract_anthropic_tool_use_blocks():
    data = {
        "content": [
            {"type": "text", "text": "أحتاج قراءة الصورة."},
            {
                "type": "tool_use",
                "id": "toolu-1",
                "name": "get_index_timeline",
                "input": {"field_id": "f1", "index": "ndvi", "days": 730},
            },
        ]
    }
    calls = provider_tooling.extract_tool_calls("messages", data)
    assert calls[0]["tool"] == "get_index_timeline"
    assert calls[0]["params"]["index"] == "ndvi"
    assert calls[0]["provider_native"] is True


def test_ai_generation_payload_accepts_provider_tools_static():
    source = Path("services/ai_agronomist/ai_generation.py").read_text(encoding="utf-8")
    assert "provider_tools" in source
    assert 'payload["tools"] = provider_tools' in source
    assert "provider_tooling.extract_tool_calls" in source
    assert "tool_calls: tuple[dict[str, Any], ...]" in source


def test_main_wires_provider_native_calls_to_governed_tool_loop_static():
    source = Path("services/ai_agronomist/main.py").read_text(encoding="utf-8")
    assert "provider_tooling.build_provider_tools" in source
    assert "provider_native_tool_calls" in source
    assert (
        "requested_tool_calls = list(req.tool_calls or []) + provider_native_tool_calls" in source
    )
    assert '"provider_native_tool_calls": provider_native_tool_calls' in source
    assert "tool_loop.run_tool_calls" in source
