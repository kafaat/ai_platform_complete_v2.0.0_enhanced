"""V58 hardening guards: native multi-round tool loop + production audit fields."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import ai_generation as G  # noqa: E402
from services.ai_agronomist import tool_loop  # noqa: E402


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _MultiRoundClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, endpoint, headers=None, json=None):
        self.__class__.calls.append(json)
        n = len(self.__class__.calls)
        if n == 1:
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
                                            "name": "get_field_state",
                                            "arguments": '{"field_id":"field-1"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            )
        if n == 2:
            # نموذج حقيقي قد يطلب أداة ثانية بعد رؤية نتيجة الأولى.
            return _Resp(
                {
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "tc-2",
                                        "type": "function",
                                        "function": {
                                            "name": "get_weather_history",
                                            "arguments": '{"field_id":"field-1","days":30}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            )
        return _Resp({"choices": [{"message": {"content": "جواب نهائي بعد جولتين."}}]})


@pytest.mark.asyncio
async def test_generate_supports_provider_native_multi_round_tool_loop(monkeypatch):
    monkeypatch.setenv("AI_GENERATION_ENABLED", "1")
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("AI_MODEL", "deepseek/deepseek-chat")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    _MultiRoundClient.calls = []
    monkeypatch.setattr(G.httpx, "AsyncClient", _MultiRoundClient)

    def fetcher(name, params):
        return {"tool": name, "field_id": params.get("field_id"), "ok": True}

    gen = await G.generate(
        "افحص الحقل ثم الطقس",
        "context",
        policy={"data_sharing_level": "redacted_external"},
        allowed_capabilities=["can_read_field_data", "can_read_historical_imagery"],
        tool_fetcher=fetcher,
        tenant_id="tenant-1",
        timestamp="2026-07-01T00:00:00Z",
        max_tool_rounds=3,
    )

    assert gen is not None
    assert gen.text == "جواب نهائي بعد جولتين."
    assert gen.tool_rounds == 2
    assert [r["tool"] for r in gen.tool_calls] == ["get_field_state", "get_weather_history"]
    assert len(_MultiRoundClient.calls) == 3
    assert _MultiRoundClient.calls[1]["messages"][3]["role"] == "tool"
    assert _MultiRoundClient.calls[2]["messages"][3]["role"] == "tool"


def test_tool_audit_contains_production_traceability_fields():
    saved = []
    out = tool_loop.run_tool_calls(
        [
            {
                "id": "tc-1",
                "tool": "get_field_state",
                "params": {"field_id": "field-1", "api_key": "secret"},
            }
        ],
        allowed_capabilities=["can_read_field_data"],
        fetcher=lambda name, params: {"field_id": params["field_id"], "state": "ok"},
        tenant_id="tenant-1",
        actor="user-1",
        timestamp="2026-07-01T00:00:00Z",
        audit_saver=saved.append,
        provider="openrouter",
        model="deepseek/deepseek-chat",
    )

    assert out["tool_calls"][0]["outcome"] == "executed"
    audit = saved[0]
    assert audit["tenant_id"] == "tenant-1"
    assert audit["actor"] == "user-1"
    assert audit["field_id"] == "field-1"
    assert audit["provider"] == "openrouter"
    assert audit["model"] == "deepseek/deepseek-chat"
    assert audit["input_hash"] and len(audit["input_hash"]) == 64
    assert audit["params"]["api_key"] == "[redacted]"
    assert "state" in audit["result_summary"] or "keys" in audit["result_summary"]
