"""اختبارات مفتاح المزوّد الموحَّد (local Ollama ↔ external Anthropic)."""

import pytest
from api.ai_provider_config import ANTHROPIC_VERSION, resolve_ai_provider

pytestmark = pytest.mark.unit


def _clear(monkeypatch):
    for k in (
        "AI_PROVIDER",
        "AI_MODEL",
        "OLLAMA_BASE_URL",
        "OLLAMA_API_KEY",
        "LOCAL_LLM_MODEL",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
    ):
        monkeypatch.delenv(k, raising=False)


def test_defaults_to_local_ollama(monkeypatch):
    _clear(monkeypatch)
    cfg = resolve_ai_provider()
    assert cfg.provider == "local"
    assert cfg.available is True  # المحلّيّ لا يحتاج مفاتيح سحابيّة
    assert cfg.messages_endpoint.endswith("/v1/messages")
    assert cfg.headers["authorization"].startswith("Bearer ")
    assert cfg.headers["anthropic-version"] == ANTHROPIC_VERSION
    # لا يُسرَّب مفتاح سحابيّ في الوضع المحلّيّ.
    assert "x-api-key" not in cfg.headers


def test_provider_aliases_normalize(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    assert resolve_ai_provider().provider == "local"
    monkeypatch.setenv("AI_PROVIDER", "claude")
    assert resolve_ai_provider().provider == "anthropic"


def test_anthropic_requires_key_and_model(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    cfg = resolve_ai_provider()
    # fail-closed: بلا مفتاح/نموذج ⇒ غير متاح بسبب صريح.
    assert cfg.provider == "anthropic"
    assert cfg.available is False
    assert "ANTHROPIC_API_KEY" in cfg.reason_ar


def test_anthropic_available_with_key_and_model(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-xyz")
    monkeypatch.setenv("AI_MODEL", "test-model")
    cfg = resolve_ai_provider()
    assert cfg.available is True
    assert cfg.model == "test-model"
    assert cfg.headers["x-api-key"] == "sk-test-xyz"
    assert cfg.headers["anthropic-version"] == ANTHROPIC_VERSION
    assert cfg.messages_endpoint == "https://api.anthropic.com/v1/messages"
    # الإسقاط الرصديّ لا يحوي الأسرار.
    snap = cfg.public_snapshot()
    assert "sk-test-xyz" not in str(snap)


def test_local_respects_overrides(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://my-ollama:11434")
    monkeypatch.setenv("AI_MODEL", "qwen3:70b")
    cfg = resolve_ai_provider()
    assert cfg.base_url == "http://my-ollama:11434"
    assert cfg.model == "qwen3:70b"
