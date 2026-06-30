"""اختبارات مفتاح المزوّد الموحَّد (local Ollama ↔ Anthropic ↔ OpenRouter)."""

import pytest
from api.ai_provider_config import (
    ANTHROPIC_VERSION,
    available_models,
    resolve_ai_provider,
)

pytestmark = pytest.mark.unit


def _clear(monkeypatch):
    for k in (
        "AI_PROVIDER",
        "AI_MODEL",
        "AI_MODELS",
        "OLLAMA_BASE_URL",
        "OLLAMA_API_KEY",
        "LOCAL_LLM_MODEL",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "OPENROUTER_BASE_URL",
        "OPENROUTER_API_KEY",
        "OPENROUTER_SITE_URL",
        "OPENROUTER_APP_TITLE",
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
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    assert resolve_ai_provider().provider == "openrouter"
    monkeypatch.setenv("AI_PROVIDER", "router")
    assert resolve_ai_provider().provider == "openrouter"


def test_openrouter_requires_key(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    cfg = resolve_ai_provider()
    # fail-closed: بلا مفتاح ⇒ غير متاح بسبب صريح.
    assert cfg.provider == "openrouter"
    assert cfg.wire_format == "openai_chat"
    assert cfg.endpoint.endswith("/chat/completions")
    assert cfg.available is False
    assert "OPENROUTER_API_KEY" in cfg.reason_ar
    # كتالوج افتراضيّ متعدّد النماذج حاضر للواجهة حتى قبل المفتاح.
    ids = {m["id"] for m in cfg.models}
    assert "deepseek/deepseek-chat" in ids


def test_openrouter_available_with_key_and_catalog(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv(
        "AI_MODELS",
        "deepseek/deepseek-chat|DeepSeek,google/gemini-3-pro|Gemini 3 Pro",
    )
    cfg = resolve_ai_provider()
    assert cfg.available is True
    assert cfg.headers["authorization"] == "Bearer sk-or-test"
    # بلا AI_MODEL ⇒ أوّل مدخل بالكتالوج هو الافتراضيّ.
    assert cfg.model == "deepseek/deepseek-chat"
    assert cfg.endpoint == "https://openrouter.ai/api/v1/chat/completions"
    # لا تُسرَّب الأسرار في الإسقاط الرصديّ.
    assert "sk-or-test" not in str(cfg.public_snapshot())


def test_requested_model_allowlist(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv(
        "AI_MODELS",
        "deepseek/deepseek-chat|DeepSeek,google/gemini-3-pro|Gemini 3 Pro",
    )
    # طلب ضمن الكتالوج يُحترَم.
    assert resolve_ai_provider("google/gemini-3-pro").model == "google/gemini-3-pro"
    # طلب خارج الكتالوج يُتجاهَل ويعود للافتراضيّ (قائمة سماح).
    assert resolve_ai_provider("evil/jailbreak-model").model == "deepseek/deepseek-chat"


def test_available_models_parses_env_catalog(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("AI_MODELS", "a/b|Alpha, c/d|Beta")
    models = available_models()
    assert models == [{"id": "a/b", "label": "Alpha"}, {"id": "c/d", "label": "Beta"}]


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
