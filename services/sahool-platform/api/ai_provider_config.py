"""تهيئة مزوّد الذكاء الاصطناعيّ الموحَّدة — مفتاح بيئة واحد يبدّل بين المحلّيّ
(Ollama) والخارجيّ (Anthropic) دون تكرار منطق.

السبب: كان البديل الخارجيّ موثَّقاً كملفّ مرجعيّ فقط (chat_proxy_reference). هذا
الملفّ يجعل التبديل فعليّاً عبر متغيّر `AI_PROVIDER`:

    AI_PROVIDER=local      (الافتراضيّ) ⇒ Ollama، واجهة Messages متوافقة مع Anthropic،
                            لا تسريب سحابيّ ولا مفاتيح. base_url من OLLAMA_BASE_URL.
    AI_PROVIDER=anthropic  ⇒ Anthropic Messages API (المفتاح من البيئة، خادميّاً فقط).

الطرفان يتكلّمان `POST /v1/messages` بنفس بنية الطلب/الترويسة، فمسار الدردشة يبقى
محايداً عن المزوّد: نحلّ هنا (base_url + headers + model) ونرسل نفس الحمولة.

صدق: نموذج Anthropic يُقرأ من البيئة (AI_MODEL/ANTHROPIC_MODEL) — لا نضمّن أيّ
معرّف نموذج في الكود. غياب المفتاح/النموذج ⇒ available=False بسبب صريح (fail-closed).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# إصدار ترويسة Anthropic الثابت (عقد الـMessages API).
ANTHROPIC_VERSION = "2023-06-01"
# نموذج Ollama المحلّيّ الافتراضيّ (يُخدَم محلّيّاً؛ لا علاقة بالسحابة).
DEFAULT_LOCAL_MODEL = "qwen3"
DEFAULT_OLLAMA_BASE_URL = "http://ollama:11434"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"


def _normalize_provider(raw: str | None) -> str:
    """يطبّع اسم المزوّد: ollama/local ⇒ local · claude/anthropic ⇒ anthropic.

    fail-safe: المجهول/الفارغ ⇒ local (المحلّيّ الآمن بلا مفاتيح سحابيّة).
    """
    p = (raw or "").strip().lower()
    if p in {"anthropic", "claude", "cloud"}:
        return "anthropic"
    return "local"


@dataclass(frozen=True)
class AIProviderConfig:
    provider: str  # 'local' | 'anthropic'
    base_url: str  # بلا /v1/messages
    model: str
    headers: dict[str, str] = field(default_factory=dict)
    available: bool = True
    reason_ar: str = ""

    @property
    def messages_endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/v1/messages"

    def public_snapshot(self) -> dict:
        """إسقاط رصديّ آمن (بلا أسرار) — للـ/healthz/deps ولوحة الإدارة."""
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model or None,
            "messages_endpoint": self.messages_endpoint,
            "available": self.available,
            "reason_ar": self.reason_ar or None,
        }


def resolve_ai_provider() -> AIProviderConfig:
    """يحلّ تهيئة المزوّد الحاليّة من البيئة (مصدر واحد للحقيقة)."""
    provider = _normalize_provider(os.getenv("AI_PROVIDER"))
    # نموذج مشترك: AI_MODEL يغلب، ثمّ المتغيّر الخاصّ بالمزوّد.
    shared_model = (os.getenv("AI_MODEL") or "").strip()

    if provider == "anthropic":
        base_url = (os.getenv("ANTHROPIC_BASE_URL") or DEFAULT_ANTHROPIC_BASE_URL).strip()
        api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        model = shared_model or (os.getenv("ANTHROPIC_MODEL") or "").strip()
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
        )

    # المحلّيّ (Ollama، متوافق مع Anthropic Messages API).
    base_url = (os.getenv("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL).strip()
    model = shared_model or (os.getenv("LOCAL_LLM_MODEL") or DEFAULT_LOCAL_MODEL).strip()
    # Ollama يقبل أيّ Bearer؛ نسمح بتجاوزه عبر OLLAMA_API_KEY عند الحاجة.
    token = (os.getenv("OLLAMA_API_KEY") or "ollama").strip()
    headers = {
        "content-type": "application/json",
        "anthropic-version": ANTHROPIC_VERSION,
        "authorization": f"Bearer {token}",
    }
    return AIProviderConfig(
        provider="local",
        base_url=base_url,
        model=model,
        headers=headers,
        available=True,
        reason_ar="",
    )
