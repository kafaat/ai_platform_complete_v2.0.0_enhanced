"""تهيئة مزوّد الذكاء الاصطناعيّ الموحَّدة — مفتاح بيئة واحد يبدّل بين المحلّيّ
(Ollama) والخارجيّ (Anthropic) ومُوجِّه نماذج متعدّد (OpenRouter) دون تكرار منطق.

السبب: كان البديل الخارجيّ موثَّقاً كملفّ مرجعيّ فقط (chat_proxy_reference). هذا
الملفّ يجعل التبديل فعليّاً عبر متغيّر `AI_PROVIDER`:

    AI_PROVIDER=local       (الافتراضيّ) ⇒ Ollama، واجهة OpenAI Chat Completions المتوافقة،
                             لا تسريب سحابيّ ولا مفاتيح. base_url من OLLAMA_BASE_URL.
    AI_PROVIDER=anthropic   ⇒ Anthropic Messages API (المفتاح من البيئة، خادميّاً فقط).
    AI_PROVIDER=openrouter  ⇒ OpenRouter (واجهة OpenAI chat/completions) — مُوجِّه يتيح
                             عدّة نماذج (DeepSeek، Claude Sonnet، Gemini 3 Pro…)
                             يُختار النموذج من كتالوج `AI_MODELS` وتختاره الواجهة.
    AI_PROVIDER=vllm       ⇒ خادم vLLM داخليّ OpenAI-compatible؛ opt-in وغير افتراضي.

المحلّيّ وOpenRouter/vLLM يتكلّمون صيغة OpenAI Chat Completions؛ Anthropic وحده
يستخدم `POST /v1/messages`. نُجرّد الفرق عبر `wire_format` و`endpoint`،
فمسار الدردشة يبقى محايداً: نحلّ هنا (base_url + headers + model + صيغة) ونرسل الحمولة
المناسبة.

صدق: لا نضمّن أيّ معرّف نموذج في الكود كقيمة سحابيّة مفروضة — النموذج يُقرأ من البيئة
(AI_MODEL أو كتالوج AI_MODELS). غياب المفتاح/النموذج للمزوّد السحابيّ ⇒ available=False
بسبب صريح (fail-closed). اختيار الواجهة يُتحقَّق دائماً مقابل قائمة سماح الكتالوج.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# إصدار ترويسة Anthropic الثابت (عقد الـMessages API).
ANTHROPIC_VERSION = "2023-06-01"
# نموذج Ollama المحلّيّ الافتراضيّ (يُخدَم محلّيّاً؛ لا علاقة بالسحابة).
DEFAULT_LOCAL_MODEL = "llama3.2:3b"
DEFAULT_OLLAMA_BASE_URL = "http://sahool-ollama:11434"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_VLLM_BASE_URL = "http://sahool-vllm-jais:8000/v1"
DEFAULT_VLLM_MODEL = "jais-natural-farmer"

# كتالوج النماذج الافتراضيّ لكلّ مزوّد حين لا يُضبَط `AI_MODELS` في البيئة.
# قيم أمثلة قابلة للتجاوز بالكامل من `.env` (المعرّفات الفعليّة يضبطها المشغّل).
_DEFAULT_CATALOG: dict[str, list[tuple[str, str]]] = {
    "openrouter": [
        ("deepseek/deepseek-chat", "DeepSeek"),
        ("anthropic/claude-sonnet-4.6", "Claude Sonnet"),
        ("google/gemini-3-pro", "Gemini 3 Pro"),
    ],
    "local": [("llama3.2:3b", "Llama 3.2 3B (محلّيّ / Ollama)")],
    "vllm": [("jais-natural-farmer", "Jais Natural Farmer (Solshine / vLLM)")],
}


def _normalize_provider(raw: str | None) -> str:
    """يطبّع اسم المزوّد: ollama/local ⇒ local · claude/anthropic ⇒ anthropic ·
    openrouter/router ⇒ openrouter.

    fail-safe: المجهول/الفارغ ⇒ local (المحلّيّ الآمن بلا مفاتيح سحابيّة).
    """
    p = (raw or "").strip().lower()
    if p in {"anthropic", "claude", "cloud"}:
        return "anthropic"
    if p in {"openrouter", "router", "or"}:
        return "openrouter"
    if p in {"vllm", "jais", "jais-natural-farmer"}:
        return "vllm"
    return "local"


def _parse_catalog(provider: str) -> list[dict[str, str]]:
    """يحلّ كتالوج النماذج القابلة للاختيار من البيئة `AI_MODELS`.

    الصيغة: مدخلات مفصولة بفاصلة، كلّ مدخل `id|label` (الـlabel اختياريّ).
    مثال: ``deepseek/deepseek-chat|DeepSeek,google/gemini-3-pro|Gemini 3 Pro``
    حين لا يُضبَط ⇒ كتالوج افتراضيّ مناسب للمزوّد (قابل للتجاوز).
    """
    raw = (os.getenv("AI_MODELS") or "").strip()
    items: list[dict[str, str]] = []
    if raw:
        for entry in raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            mid, _, label = entry.partition("|")
            mid = mid.strip()
            if not mid:
                continue
            items.append({"id": mid, "label": (label.strip() or mid)})
    if not items:
        for mid, label in _DEFAULT_CATALOG.get(provider, []):
            items.append({"id": mid, "label": label})
    return items


def available_models(provider: str | None = None) -> list[dict[str, str]]:
    """قائمة النماذج المتاحة للاختيار (للواجهة/لوحة الإدارة) — بلا أسرار."""
    prov = _normalize_provider(provider if provider is not None else os.getenv("AI_PROVIDER"))
    return _parse_catalog(prov)


def _resolve_model(provider: str, shared_model: str, requested: str | None) -> str:
    """يختار النموذج الفعليّ مع احترام قائمة سماح الكتالوج.

    أولويّة: طلب الواجهة (إن كان ضمن الكتالوج) ⇒ AI_MODEL ⇒ أوّل مدخل بالكتالوج.
    طلب خارج الكتالوج يُتجاهَل (أمان: لا يُمرّر المستخدم معرّفاً عشوائيّاً للمزوّد).
    """
    catalog = _parse_catalog(provider)
    allowed = {m["id"] for m in catalog}
    req = (requested or "").strip()
    if req and req in allowed:
        return req
    # Fail closed for providers with a declared catalog: a stale global AI_MODEL
    # must never cross provider boundaries (e.g. qwen3 -> vLLM/Jais). Providers
    # without a default catalog (Anthropic) may still use an operator-supplied model.
    if shared_model and (not allowed or shared_model in allowed):
        return shared_model
    return catalog[0]["id"] if catalog else ""


@dataclass(frozen=True)
class AIProviderConfig:
    provider: str  # 'local' | 'vllm' | 'anthropic' | 'openrouter'
    base_url: str  # بلا مسار النهاية
    model: str
    headers: dict[str, str] = field(default_factory=dict)
    available: bool = True
    reason_ar: str = ""
    wire_format: str = "messages"  # 'messages' (Anthropic) | 'openai_chat' (Ollama/vLLM/OpenRouter)
    models: list[dict[str, str]] = field(default_factory=list)

    @property
    def messages_endpoint(self) -> str:
        """عقد Anthropic Messages دون مضاعفة ``/v1`` في اللقطة الرصديّة."""
        base = self.base_url.rstrip("/")
        return f"{base}/messages" if base.endswith("/v1") else f"{base}/v1/messages"

    @property
    def endpoint(self) -> str:
        """نقطة النهاية الفعليّة حسب صيغة السلك (messages ↔ openai_chat)."""
        if self.wire_format == "openai_chat":
            return f"{self.base_url.rstrip('/')}/chat/completions"
        return self.messages_endpoint

    def public_snapshot(self) -> dict:
        """إسقاط رصديّ آمن (بلا أسرار) — للـ/healthz/deps ولوحة الإدارة."""
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model or None,
            "wire_format": self.wire_format,
            "endpoint": self.endpoint,
            "messages_endpoint": self.messages_endpoint,
            "available": self.available,
            "reason_ar": self.reason_ar or None,
            "models": self.models,
        }


def resolve_ai_provider(requested_model: str | None = None) -> AIProviderConfig:
    """يحلّ تهيئة المزوّد الحاليّة من البيئة (مصدر واحد للحقيقة).

    `requested_model` (اختياريّ، من الواجهة) يُتحقَّق مقابل كتالوج المزوّد؛ خارج
    الكتالوج يُتجاهَل ويُستعمل الافتراضيّ (قائمة سماح).
    """
    provider = _normalize_provider(os.getenv("AI_PROVIDER"))
    # نموذج مشترك: AI_MODEL يغلب، ثمّ المتغيّر الخاصّ بالمزوّد.
    shared_model = (os.getenv("AI_MODEL") or "").strip()
    catalog = _parse_catalog(provider)

    if provider == "anthropic":
        base_url = (os.getenv("ANTHROPIC_BASE_URL") or DEFAULT_ANTHROPIC_BASE_URL).strip()
        api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        anthropic_default = shared_model or (os.getenv("ANTHROPIC_MODEL") or "").strip()
        model = _resolve_model("anthropic", anthropic_default, requested_model)
        headers = {
            "content-type": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
        }
        if api_key:
            headers["x-api-key"] = api_key
        missing = []
        if not api_key:
            missing.append("ANTHROPIC_API_KEY")
        if not model:
            missing.append("AI_MODEL (أو ANTHROPIC_MODEL)")
        available = not missing
        reason = "" if available else f"المزوّد anthropic يحتاج: {', '.join(missing)}."
        return AIProviderConfig(
            provider="anthropic",
            base_url=base_url,
            model=model,
            headers=headers,
            available=available,
            reason_ar=reason,
            wire_format="messages",
            models=catalog,
        )

    if provider == "vllm":
        base_url = (os.getenv("VLLM_BASE_URL") or DEFAULT_VLLM_BASE_URL).strip()
        token = (os.getenv("VLLM_API_KEY") or "sahool-vllm-local").strip()
        default_model = shared_model or (os.getenv("VLLM_MODEL") or DEFAULT_VLLM_MODEL).strip()
        model = _resolve_model("vllm", default_model, requested_model)
        headers = {"content-type": "application/json"}
        if token:
            headers["authorization"] = f"Bearer {token}"
        return AIProviderConfig(
            provider="vllm",
            base_url=base_url,
            model=model,
            headers=headers,
            available=bool(model and base_url),
            reason_ar="" if model and base_url else "المزوّد vllm يحتاج VLLM_BASE_URL ونموذجاً.",
            wire_format="openai_chat",
            models=catalog,
        )

    if provider == "openrouter":
        base_url = (os.getenv("OPENROUTER_BASE_URL") or DEFAULT_OPENROUTER_BASE_URL).strip()
        api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        model = _resolve_model("openrouter", shared_model, requested_model)
        headers = {
            "content-type": "application/json",
        }
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"
        # ترويسات OpenRouter الإرشاديّة (اختياريّة، للوسم/التصنيف) — لا أسرار.
        referer = (os.getenv("OPENROUTER_SITE_URL") or "").strip()
        title = (os.getenv("OPENROUTER_APP_TITLE") or "SAHOOL").strip()
        if referer:
            headers["http-referer"] = referer
        if title:
            headers["x-title"] = title
        missing = []
        if not api_key:
            missing.append("OPENROUTER_API_KEY")
        if not model:
            missing.append("AI_MODEL (أو كتالوج AI_MODELS)")
        available = not missing
        reason = "" if available else f"المزوّد openrouter يحتاج: {', '.join(missing)}."
        return AIProviderConfig(
            provider="openrouter",
            base_url=base_url,
            model=model,
            headers=headers,
            available=available,
            reason_ar=reason,
            wire_format="openai_chat",
            models=catalog,
        )

    # المحلّيّ (Ollama) يستخدم واجهة OpenAI-compatible الموثّقة /v1/chat/completions.
    # لا نعتمد Anthropic /v1/messages لأن الصورة التاريخية في هذا الخط لا تضمنها.
    root_url = (os.getenv("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL).strip().rstrip("/")
    base_url = f"{root_url}/v1"
    local_default = shared_model or (os.getenv("LOCAL_LLM_MODEL") or DEFAULT_LOCAL_MODEL).strip()
    model = _resolve_model("local", local_default, requested_model)
    token = (os.getenv("OLLAMA_API_KEY") or "ollama").strip()
    headers = {"content-type": "application/json", "authorization": f"Bearer {token}"}
    return AIProviderConfig(
        provider="local",
        base_url=base_url,
        model=model,
        headers=headers,
        available=bool(model and root_url),
        reason_ar="" if model and root_url else "المزوّد المحلي يحتاج نموذجاً ضمن الكتالوج.",
        wire_format="openai_chat",
        models=catalog,
    )
