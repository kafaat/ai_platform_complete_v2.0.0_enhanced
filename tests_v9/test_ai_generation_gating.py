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


@pytest.mark.asyncio
async def test_generate_returns_none_when_disabled(gen, monkeypatch):
    _clear(monkeypatch)
    # الراية مُعطَّلة ⇒ لا استدعاء شبكيّ، None فوراً.
    result = await gen.generate("سؤال", "أدلّة", "deepseek/deepseek-chat")
    assert result is None
