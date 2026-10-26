"""Tool results must be redacted, not only the evidence context, in ``redacted_external``.

When a tenant allows external generation only in redacted form, every byte that leaves
for OpenRouter/Anthropic must go through the same redaction as the evidence context.
Tool results (``get_weather_history`` / ``get_drawings_and_zones`` …) used to be sent
verbatim, carrying the owner's e-mail, phone, field UUID and the field's coordinates as
JSON numbers. The provider is mocked with ``httpx.MockTransport``; nothing leaves the box.
"""

from __future__ import annotations

import asyncio
import json

import pytest

pytestmark = pytest.mark.unit

httpx = pytest.importorskip("httpx")

from services.ai_agronomist import ai_generation as G  # noqa: E402

_EMAIL = "farmer@example.com"
_PHONE_DIGITS = "777123456"
_UUID = "123e4567-e89b-12d3-a456-426614174000"
_LAT = "15.123456"
_LON = "44.654321"
_PIVOT_LAT = "15.354321"
_PIVOT_LON = "44.206789"
_SECRETS = (_EMAIL, _UUID, _LAT, _LON, _PIVOT_LAT, _PIVOT_LON)


def _fetcher(name, params):
    if name == "get_weather_history":
        return {
            "field_id": "f1",
            "weather_history": {
                "available": True,
                "location": {"lat": 15.123456, "lon": 44.654321},
                "summary": {"days": 30},
            },
        }
    return {
        "drawing_context": {
            "owner_email": _EMAIL,
            "field_uuid": _UUID,
            "pivot": f"{_PIVOT_LAT}, {_PIVOT_LON}",
            "phone": "+967 777 123 456",
            "centroid": [44.654321, 15.123456],
            "zones": [{"name": "z1", "coordinates": [[[44.654321, 15.123456]]]}],
        }
    }


def _first_response(wire: str, tool: str) -> dict:
    args = {"field_id": "f1", "days": 30} if tool == "get_weather_history" else {"field_id": "f1"}
    if wire == "openai_chat":
        return {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {"name": tool, "arguments": json.dumps(args)},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    return {
        "content": [{"type": "tool_use", "id": "toolu_1", "name": tool, "input": args}],
        "stop_reason": "tool_use",
    }


def _final_response(wire: str) -> dict:
    if wire == "openai_chat":
        return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
    return {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}


def _run(monkeypatch, *, provider: str, tool: str, native_fails: bool, mode: str):
    for k in ("AI_MODELS", "AI_MODEL", "ANTHROPIC_MODEL", "OPENROUTER_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AI_GENERATION_ENABLED", "1")
    monkeypatch.setenv("AI_PROVIDER", provider)
    if provider == "openrouter":
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        monkeypatch.setenv("AI_MODEL", "deepseek/deepseek-chat")
    else:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test")
    cfg = G.resolve_generation()
    assert cfg is not None and G.provider_is_external(cfg.provider)
    wire = cfg.wire_format

    sent: list[str] = []

    def handler(req):
        sent.append(req.content.decode("utf-8"))
        if len(sent) == 1:
            return httpx.Response(200, json=_first_response(wire, tool))
        if len(sent) == 2 and native_fails:
            return httpx.Response(400, json={"error": "unsupported"})
        return httpx.Response(200, json=_final_response(wire))

    orig = httpx.AsyncClient

    class _Client(orig):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **k)

    monkeypatch.setattr(G.httpx, "AsyncClient", _Client)
    result = asyncio.run(
        G.generate(
            "q",
            f"owner {_EMAIL} at {_LAT}, {_LON}",
            policy={"data_sharing_level": mode},
            allowed_capabilities=["can_read_field_data", "can_read_historical_imagery"],
            tool_fetcher=_fetcher,
            tenant_id="t1",
            max_tool_rounds=3,
            allowed_tools={tool},
        )
    )
    assert result is not None and result.text == "ok"
    assert len(sent) >= 2, "the tool result never reached the provider"
    return sent


@pytest.mark.parametrize("provider", ["openrouter", "anthropic"])
@pytest.mark.parametrize("tool", ["get_weather_history", "get_drawings_and_zones"])
@pytest.mark.parametrize("native_fails", [False, True])
def test_redacted_external_never_sends_tool_result_identifiers(
    monkeypatch, provider, tool, native_fails
):
    sent = _run(
        monkeypatch,
        provider=provider,
        tool=tool,
        native_fails=native_fails,
        mode="redacted_external",
    )
    # Every request after the first carries tool results; none may hold a raw identifier.
    for body in sent:
        for secret in _SECRETS:
            assert secret not in body, f"{secret!r} leaked to {provider}"
        compact = "".join(ch for ch in body if ch.isdigit())
        assert _PHONE_DIGITS not in compact, f"phone leaked to {provider}"


def test_full_external_still_sends_tool_results_verbatim(monkeypatch):
    sent = _run(
        monkeypatch,
        provider="openrouter",
        tool="get_weather_history",
        native_fails=False,
        mode="full_external",
    )
    tool_msgs = [m for m in json.loads(sent[1])["messages"] if m["role"] == "tool"]
    assert tool_msgs and _LAT in tool_msgs[0]["content"] and _LON in tool_msgs[0]["content"]


def test_structured_redaction_covers_coordinate_keys_and_arrays():
    data = {
        "lat": 15.1,
        "Longitude": 44.2,
        "lng": 1,
        "bbox": [44.0, 15.0, 44.1, 15.1],
        "geometry": {"type": "Polygon", "coordinates": [[[44.0, 15.0]]]},
        "area_ha": 12.5,
        "note": "mail a@b.co",
    }
    out = G.redact_structured_for_external(data)
    assert out["area_ha"] == 12.5
    assert "a@b.co" not in out["note"]
    for key in ("lat", "Longitude", "lng", "bbox", "geometry"):
        assert out[key] == "[redacted-coordinates]"
