"""اختبارات مفتاح المزوّد الموحَّد (Ollama ↔ vLLM/Jais ↔ Anthropic ↔ OpenRouter)."""

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
        "VLLM_BASE_URL",
        "VLLM_API_KEY",
        "VLLM_MODEL",
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
    assert cfg.wire_format == "openai_chat"
    assert cfg.endpoint.endswith("/v1/chat/completions")
    assert cfg.headers["authorization"].startswith("Bearer ")
    assert "anthropic-version" not in cfg.headers
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
    monkeypatch.setenv("AI_PROVIDER", "jais")
    assert resolve_ai_provider().provider == "vllm"


def test_vllm_is_opt_in_internal_openai_provider(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "vllm")
    cfg = resolve_ai_provider()
    assert cfg.provider == "vllm"
    assert cfg.available is True
    assert cfg.wire_format == "openai_chat"
    assert cfg.model == "jais-natural-farmer"
    assert cfg.endpoint == "http://sahool-vllm-jais:8000/v1/chat/completions"
    # لا بديلَ مُصلَّب بعد اليوم: كان `sahool-vllm-local` قيمةً في **الشيفرة**، فتنظيف
    # `.env.example` وcompose منها كان تجميلاً — السرّ يبقى منشوراً في مصدرين
    # إنتاجيّين. فالمقيس الآن أنّ غياب المفتاح **لا يُرسِل مصادقة** بدل أن يُرسِل
    # مصادقةً يعرفها كلّ من قرأ المستودع.
    assert "authorization" not in cfg.headers, (
        "بلا `VLLM_API_KEY` تُرسَل ترويسة مصادقة — أي أنّ بديلاً مُصلَّباً عاد"
    )

    # والاتّجاه الآخر: المضبوط يُرسَل، ولا يتسرّب إلى اللقطة العامّة.
    monkeypatch.setenv("VLLM_API_KEY", "k-from-operator")
    configured = resolve_ai_provider()
    assert configured.headers["authorization"] == "Bearer k-from-operator"
    assert "k-from-operator" not in str(configured.public_snapshot())


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
    monkeypatch.setenv("LOCAL_LLM_MODEL", "llama3.2:3b")
    cfg = resolve_ai_provider()
    assert cfg.base_url == "http://my-ollama:11434/v1"
    assert cfg.model == "llama3.2:3b"
    assert cfg.endpoint == "http://my-ollama:11434/v1/chat/completions"


# ──────────────────────────────────────────────────────────────────────────
# OpenRouter: تفضيلات التوجيه للخصوصيّة + رفض نماذج ``:free``.
# المصدر الأوّليّ: أنواع SDK الرسميّة لـOpenRouter (OpenRouterTeam/typescript-sdk
# ``src/models/providerpreferences.ts``) — ``provider: {data_collection, zdr}``.
# ──────────────────────────────────────────────────────────────────────────
_NO_TRAINING = {"data_collection": "deny", "zdr": True}


def test_openrouter_request_extras_carry_privacy_preferences(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    cfg = resolve_ai_provider()
    assert cfg.available is True
    assert cfg.request_extras == {"provider": _NO_TRAINING}
    # نسخة مستقلّة في كلّ قراءة: تعديلها لا يُرخي الطلب التالي.
    cfg.request_extras["provider"]["zdr"] = False
    assert cfg.request_extras == {"provider": _NO_TRAINING}


def test_request_extras_are_openrouter_only(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("AI_MODEL", "test-model")
    for provider in ("local", "vllm", "anthropic"):
        monkeypatch.setenv("AI_PROVIDER", provider)
        assert resolve_ai_provider().request_extras == {}, provider


@pytest.mark.parametrize(
    ("model_env", "catalog_env", "refused_id"),
    [
        ("meta-llama/llama-3.3-70b-instruct:free", None, "meta-llama/llama-3.3-70b-instruct:free"),
        (
            "deepseek/deepseek-chat",
            "deepseek/deepseek-chat|DeepSeek,deepseek/deepseek-r1:free|R1 Free",
            "deepseek/deepseek-r1:free",
        ),
        (None, "qwen/qwen3-coder:FREE|Qwen", "qwen/qwen3-coder:FREE"),
    ],
)
def test_openrouter_free_model_refused_with_clear_reason(
    monkeypatch, model_env, catalog_env, refused_id
):
    """نموذج ``:free`` في تهيئة OpenRouter ⇒ ``available=False`` بسبب صريح يسمّيه —
    فيرفض مسار الدردشة بـ503 بدل أن يُرسِل المطالبة."""
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    if model_env:
        monkeypatch.setenv("AI_MODEL", model_env)
    if catalog_env:
        monkeypatch.setenv("AI_MODELS", catalog_env)
    cfg = resolve_ai_provider("deepseek/deepseek-chat")
    assert cfg.available is False
    assert ":free" in cfg.reason_ar
    assert refused_id in cfg.reason_ar


def test_free_suffix_refusal_is_openrouter_only(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_MODELS", "my-farm-model:free|Local")
    cfg = resolve_ai_provider()
    assert cfg.available is True
    assert cfg.model == "my-farm-model:free"


_OPENROUTER_CATALOG = "deepseek/deepseek-chat|DeepSeek,google/gemini-3-pro|Gemini 3 Pro"


def test_leftover_openrouter_catalog_does_not_override_anthropic_model(monkeypatch):
    """`AI_MODELS` is global: switching to Anthropic with an OpenRouter catalog still set
    must resolve ANTHROPIC_MODEL, never send `deepseek/deepseek-chat` to Anthropic."""
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("AI_MODELS", _OPENROUTER_CATALOG)
    cfg = resolve_ai_provider()
    assert cfg.model == "claude-sonnet-4-6"
    assert cfg.models == []
    # A UI request for a leftover catalog id is not an allowlisted Anthropic model.
    assert resolve_ai_provider("deepseek/deepseek-chat").model == "claude-sonnet-4-6"


def test_leftover_catalog_without_anthropic_model_fails_closed(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("AI_MODELS", _OPENROUTER_CATALOG)
    cfg = resolve_ai_provider()
    assert cfg.model == ""
    assert cfg.available is False


def test_openrouter_catalog_drops_ids_from_another_provider(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("AI_MODELS", "claude-sonnet-4-6|Claude," + _OPENROUTER_CATALOG)
    cfg = resolve_ai_provider()
    assert cfg.model == "deepseek/deepseek-chat"
    assert [m["id"] for m in cfg.models] == ["deepseek/deepseek-chat", "google/gemini-3-pro"]
