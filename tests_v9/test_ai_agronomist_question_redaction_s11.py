"""S11 (audit 2026-11-01): in ``redacted_external`` the evidence context was redacted but
the user's question (phone/email/coordinates) left for the external provider verbatim.
The provider is mocked with ``httpx.MockTransport``; nothing leaves the box.
"""

from __future__ import annotations

import asyncio
import json

import pytest

pytestmark = pytest.mark.unit

httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

from services.ai_agronomist import ai_generation as G  # noqa: E402

_EMAIL = "farmer@example.com"
_PHONE = "+967 777 123 456"
_PHONE_DIGITS = "967777123456"
_LAT, _LON = "15.369445", "44.191006"


def _ask(monkeypatch, provider: str, mode: str) -> list[str]:
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
    sent: list[str] = []

    def handler(req):
        sent.append(req.content.decode("utf-8"))
        if cfg.wire_format == "openai_chat":
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    orig = httpx.AsyncClient

    class _Client(orig):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **k)

    monkeypatch.setattr(G.httpx, "AsyncClient", _Client)
    question = f"اتصل بي على {_PHONE} أو {_EMAIL}؛ موقع الحقل {_LAT}, {_LON} — متى أسقي؟"
    result = asyncio.run(
        G.generate(question, "evidence", policy={"data_sharing_level": mode}, max_tool_rounds=0)
    )
    assert result is not None and result.text == "ok"
    assert sent, "the provider was never called"
    return sent


@pytest.mark.parametrize("provider", ["openrouter", "anthropic"])
def test_s11_redacted_external_redacts_the_question(monkeypatch, provider):
    sent = _ask(monkeypatch, provider, "redacted_external")
    for body in sent:
        text = json.loads(body)
        flat = json.dumps(text, ensure_ascii=False)
        assert _EMAIL not in flat, "email leaked"
        assert _LAT not in flat and _LON not in flat, "coordinates leaked"
        assert _PHONE_DIGITS not in "".join(ch for ch in flat if ch.isdigit()), "phone leaked"
        assert "متى أسقي" in flat, "the question itself must still reach the provider"


def test_s11_full_external_keeps_the_question_verbatim(monkeypatch):
    sent = _ask(monkeypatch, "openrouter", "full_external")
    assert _EMAIL in json.loads(sent[0])["messages"][1]["content"]
