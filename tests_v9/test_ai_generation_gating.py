"""اختبار بوّابات التوليد الاختياريّ للمستشار (services/ai_agronomist/ai_generation.py).

يثبت قيود الأمان المطلوبة بلا أيّ شبكة (منطق نقيّ، مُعلَّم unit):
  • الراية العامّة AI_GENERATION_ENABLED مُعطَّلة افتراضيّاً.
  • سياسة المستأجِر تستطيع المنع الصريح.
  • OpenRouter يحتاج OPENROUTER_API_KEY (fail-closed ⇒ None ⇒ سقوط إلى الأدلّة).
  • النموذج يُتحقَّق مقابل كتالوج AI_MODELS (قائمة سماح).
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
GEN_PATH = os.path.join(ROOT, "services/ai_agronomist/ai_generation.py")


@pytest.fixture(scope="module")
def gen():
    pytest.importorskip("httpx")
    spec = importlib.util.spec_from_file_location("sahool_ai_generation_test", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    # سجّل الوحدة قبل التنفيذ كي يحلّ dataclass تلميحات النوع (يبحث في sys.modules).
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _clear(monkeypatch):
    for k in (
        "AI_GENERATION_ENABLED",
        "AI_PROVIDER",
        "AI_MODEL",
        "AI_MODELS",
        "OPENROUTER_API_KEY",
        "OPENROUTER_BASE_URL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "OLLAMA_BASE_URL",
    ):
        monkeypatch.delenv(k, raising=False)


def test_generation_disabled_by_default(gen, monkeypatch):
    _clear(monkeypatch)
    assert gen.generation_enabled() is False
    monkeypatch.setenv("AI_GENERATION_ENABLED", "true")
    assert gen.generation_enabled() is True


def test_tenant_policy_can_deny(gen):
    assert gen.tenant_allows_generation(None) is True
    assert gen.tenant_allows_generation({}) is True
    assert gen.tenant_allows_generation({"ai_generation": "deny"}) is False
    assert gen.tenant_allows_generation({"ai_generation_allowed": False}) is False


def test_openrouter_requires_key(gen, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("AI_MODEL", "deepseek/deepseek-chat")
    # بلا مفتاح ⇒ None (سقوط آمن إلى الأدلّة).
    assert gen.resolve_generation() is None
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    cfg = gen.resolve_generation()
    assert cfg is not None
    assert cfg.provider == "openrouter"
    assert cfg.wire_format == "openai_chat"
    assert cfg.endpoint.endswith("/chat/completions")
    assert cfg.headers["authorization"] == "Bearer sk-or-test"
    assert cfg.model == "deepseek/deepseek-chat"


def test_model_allowlist_enforced(gen, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("AI_MODEL", "deepseek/deepseek-chat")
    monkeypatch.setenv("AI_MODELS", "deepseek/deepseek-chat|DeepSeek,google/gemini-3-pro|Gemini")
    # طلب ضمن الكتالوج يُحترَم.
    assert gen.resolve_generation("google/gemini-3-pro").model == "google/gemini-3-pro"
    # طلب خارج الكتالوج يُتجاهَل ويعود للافتراضيّ (قائمة سماح).
    assert gen.resolve_generation("evil/jailbreak").model == "deepseek/deepseek-chat"


def test_generation_requested_model_falls_back_to_default_catalog_when_ai_models_missing(
    gen, monkeypatch
):
    """H-AI-1: حين يغيب ``AI_MODELS`` يجب أن يبقى النموذج المطلوب محكوماً بالكتالوج الافتراضيّ.

    قبل الإصلاح: كتالوج فارغ ⇒ **أيّ** نموذج مطلوب يُقبَل (تجاوز allowlist). بعده: يُرفَض
    الخارج عن الكتالوج الافتراضيّ ويعود إلى ``AI_MODEL`` الموثوق (fail-closed).
    """
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("AI_MODEL", "deepseek/deepseek-chat")
    # AI_MODELS غير مضبوط عمداً (الحالة الحرجة).
    # نموذج خبيث خارج الكتالوج الافتراضيّ ⇒ يُرفَض ويعود للافتراضيّ الموثوق.
    assert gen.resolve_generation("evil/jailbreak").model == "deepseek/deepseek-chat"
    # نموذج ضمن الكتالوج الافتراضيّ ⇒ يُقبَل (قائمة السماح الافتراضيّة فعّالة).
    assert gen.resolve_generation("google/gemini-3-pro").model == "google/gemini-3-pro"


@pytest.mark.asyncio
async def test_generate_returns_none_when_disabled(gen, monkeypatch):
    _clear(monkeypatch)
    # الراية مُعطَّلة ⇒ لا استدعاء شبكيّ، None فوراً.
    result = await gen.generate("سؤال", "أدلّة", "deepseek/deepseek-chat")
    assert result is None


# ──────────────────────────────────────────────────────────────────────────
# OpenRouter: تفضيلات التوجيه للخصوصيّة + رفض نماذج ``:free``.
# المصدر الأوّليّ لأسماء الحقول: أنواع SDK الرسميّة لـOpenRouter
# (OpenRouterTeam/typescript-sdk ``src/models/providerpreferences.ts`` و``chatrequest.ts``):
# جسم chat/completions يحمل ``provider: {data_collection: "deny", zdr: true}``.
# ──────────────────────────────────────────────────────────────────────────
_NO_TRAINING = {"data_collection": "deny", "zdr": True}


def _openrouter_env(monkeypatch, **extra):
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_openrouter_payloads_carry_no_training_provider_preferences(gen, monkeypatch):
    """كلّ حمولة تُبنى لـOpenRouter (الأولى · نتائج الأدوات الأصليّة · السقوط النصّيّ)
    تحمل ``provider`` بـ``data_collection=deny`` و``zdr=true``."""
    _openrouter_env(monkeypatch, AI_MODEL="deepseek/deepseek-chat")
    cfg = gen.resolve_generation()
    assert cfg is not None and cfg.provider == "openrouter"
    first = gen._build_payload(cfg, "سؤال", "أدلّة", 100)
    fallback = gen._build_payload(cfg, "سؤال", "أدلّة", 100, tool_results=[{"tool": "t"}])
    native = gen._build_native_tool_result_payload(
        cfg,
        "سؤال",
        "أدلّة",
        100,
        provider_calls=[{"id": "c1", "tool": "get_field_state", "params": {}}],
        tool_results=[{"tool": "get_field_state", "outcome": "executed"}],
        tools=None,
    )
    for payload in (first, fallback, native):
        assert payload["provider"] == _NO_TRAINING
    # نسخة مستقلّة لكلّ حمولة: تعديل واحدة لا يمسّ الثابت ولا الحمولات التالية.
    first["provider"]["data_collection"] = "allow"
    assert gen._build_payload(cfg, "سؤال", "أدلّة", 100)["provider"] == _NO_TRAINING


def test_non_openrouter_payloads_carry_no_provider_preferences(gen):
    """الحقل خاصّ بـOpenRouter: لا يُرسَل للمحلّيّ ولا vLLM ولا Anthropic."""
    for cfg in (
        gen.GenConfig("local", "http://x/v1/chat/completions", {}, "m", "openai_chat"),
        gen.GenConfig("vllm", "http://x/chat/completions", {}, "m", "openai_chat"),
        gen.GenConfig("anthropic", "http://x/v1/messages", {}, "m", "messages"),
    ):
        first = gen._build_payload(cfg, "سؤال", "أدلّة", 100)
        native = gen._build_native_tool_result_payload(
            cfg,
            "سؤال",
            "أدلّة",
            100,
            provider_calls=[{"id": "c1", "tool": "get_field_state", "params": {}}],
            tool_results=[{"tool": "get_field_state", "outcome": "executed"}],
            tools=None,
        )
        assert "provider" not in first, cfg.provider
        assert "provider" not in native, cfg.provider


class _RecordingClient:
    """عميل httpx مزيّف يسجّل كلّ جسم POST — يثبت ما يغادر الخدمة فعلاً على السلك."""

    posts: list = []
    responses: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, endpoint, headers=None, json=None):
        type(self).posts.append(json)
        status, body = type(self).responses.pop(0)

        class _Resp:
            status_code = status

            @staticmethod
            def json():
                return body

        return _Resp()


async def test_generate_sends_privacy_preferences_on_every_openrouter_post(gen, monkeypatch):
    """المسار الحقيقيّ ``generate``: الطلب الأوّل، وجولة نتائج الأدوات، والسقوط النصّيّ بعد
    رفض المزوّد — ثلاث نقاط POST، وكلّها تحمل تفضيلات الخصوصيّة."""
    _openrouter_env(monkeypatch, AI_GENERATION_ENABLED="1", AI_MODEL="deepseek/deepseek-chat")
    tool_call = {
        "id": "tc-1",
        "type": "function",
        "function": {
            "name": "get_truecolor_scene",
            "arguments": '{"field_id":"field-1","date":"2026-06-01"}',
        },
    }
    _RecordingClient.posts = []
    _RecordingClient.responses = [
        (200, {"choices": [{"message": {"content": None, "tool_calls": [tool_call]}}]}),
        (400, {"error": "native tool_result rejected"}),
        (200, {"choices": [{"message": {"content": "جواب نهائيّ."}}]}),
    ]
    monkeypatch.setattr(gen.httpx, "AsyncClient", _RecordingClient)
    result = await gen.generate(
        "ما حالة صورة الحقل؟",
        "context",
        policy={"data_sharing_level": "redacted_external"},
        allowed_capabilities=["can_read_field_data", "can_read_historical_imagery"],
        tool_fetcher=lambda name, params: {"scene": "truecolor"},
        tenant_id="tenant-1",
        timestamp="2026-07-01T00:00:00Z",
    )
    assert result is not None and result.text.startswith("جواب نهائيّ.")
    assert len(_RecordingClient.posts) == 3
    for payload in _RecordingClient.posts:
        assert payload["provider"] == _NO_TRAINING


@pytest.mark.parametrize(
    "extra",
    [
        # النموذج الافتراضيّ نفسه مجّانيّ.
        {"AI_MODEL": "meta-llama/llama-3.3-70b-instruct:free"},
        # الكتالوج يعرض نموذجاً مجّانيّاً ولو كان الافتراضيّ مدفوعاً.
        {
            "AI_MODEL": "deepseek/deepseek-chat",
            "AI_MODELS": "deepseek/deepseek-chat|DeepSeek,deepseek/deepseek-r1:free|R1 Free",
        },
        # حالة الأحرف لا تُفلِت الرفض.
        {"AI_MODELS": "qwen/qwen3-coder:FREE|Qwen"},
    ],
)
def test_openrouter_free_model_is_refused(gen, monkeypatch, extra):
    """نموذج ``:free`` في تهيئة OpenRouter ⇒ رفض التهيئة كلّها (fail-closed) بسبب صريح
    يسمّي المعرّف — لا اختيار صامت لنموذج آخر."""
    _openrouter_env(monkeypatch, **extra)
    assert gen.resolve_generation() is None
    assert gen.resolve_generation("deepseek/deepseek-chat") is None
    reason = gen.openrouter_config_error()
    assert ":free" in reason
    configured = [v.split("|")[0] for v in ",".join(extra.values()).split(",")]
    for model_id in configured:
        if model_id.lower().endswith(":free"):
            assert model_id in reason


def test_free_suffix_refusal_is_openrouter_only(gen, monkeypatch):
    """اللاحقة تُرفَض لـOpenRouter فقط: وسم Ollama محلّيّ اسمه ``…:free`` لا يغادر الحدّ."""
    _clear(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_MODELS", "my-farm-model:free|Local")
    cfg = gen.resolve_generation()
    assert cfg is not None and cfg.model == "my-farm-model:free"
    assert gen.openrouter_config_error() == ""
    # والتهيئة الافتراضيّة لـOpenRouter (بلا AI_MODELS) خالية من ``:free`` فلا تُرفَض.
    _openrouter_env(monkeypatch)
    assert gen.openrouter_config_error() == ""
    assert gen.resolve_generation() is not None
