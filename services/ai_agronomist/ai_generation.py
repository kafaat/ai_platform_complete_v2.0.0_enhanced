"""توليد نصّ مُؤرَّض اختياريّ للمستشار (مسار سحابيّ عبر OpenRouter/Anthropic أو محلّيّ
Ollama) فوق طبقة RAG+KG الأساسيّة — لا يحلّ محلّها بل يُركّب جواباً تفسيريّاً منها.

قيود الأمان (مطلوبة، fail-closed):
  • خلف راية عامّة ``AI_GENERATION_ENABLED`` (افتراضيّ off) + سياسة المستأجِر (تستطيع
    المنع). أيّ منهما يمنع ⇒ لا توليد.
  • المفتاح من البيئة فقط (``OPENROUTER_API_KEY`` / ``ANTHROPIC_API_KEY``) — لا يصل
    الكود ولا الواجهة.
  • النموذج يُتحقَّق مقابل كتالوج ``AI_MODELS`` (قائمة سماح)؛ طلب خارجها ⇒ الافتراضيّ.
  • fail-safe: غياب راية/مفتاح/نموذج أو أيّ فشل مزوّد ⇒ تُعيد الدوالّ ``None`` فيسقط
    المستدعي إلى جواب الأدلّة الحاليّ (RAG+KG) بلا انقطاع. لا تُرفَع استثناءات للمستدعي.
  • النصّ المُولَّد تفسيريّ/استشاريّ مؤرَّض فقط — القرار التنفيذيّ يبقى للمنسّق والحواجز.

أسماء المتغيّرات مطابقة لـ``sahool-platform/api/ai_provider_config`` كي يبقى ``.env``
مصدراً واحداً للتهيئة عبر الخدمات (الكود معزول لكلّ خدمة، التهيئة مشتركة).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

logger = logging.getLogger("ai_agronomist.generation")

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_OLLAMA_BASE_URL = "http://ollama:11434"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# نظام تأريض صارم: يُجيب من الأدلّة المُمرَّرة فقط، لا قرارات تنفيذيّة، لا تلفيق.
_GROUNDED_SYSTEM_AR = (
    "أنت مستشار زراعيّ لمنصّة «سهول». أجب حصراً اعتماداً على «الأدلّة» المُعطاة "
    "(سياق RAG + روابط Knowledge Graph + حالة الحقل). لا تخترع أرقاماً أو مصادر، وإن "
    "نقصت الأدلّة فقل ذلك بصدق. هذا تفسير استشاريّ فقط؛ القرار التنفيذيّ النهائيّ يعود "
    "لمنسّق ذكاء الحقل والحواجز. أجب بالعربيّة الفصحى بإيجاز (٣–٥ جمل) وبدقّة في الوحدات."
)


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def generation_enabled() -> bool:
    """الراية العامّة — افتراضيّاً مُعطَّلة (الإبقاء على نمط الأدلّة فقط)."""
    return _truthy(os.getenv("AI_GENERATION_ENABLED"))


def tenant_allows_generation(policy: dict | None) -> bool:
    """سياسة المستأجِر: تمنع التوليد إن نصّت صراحةً على ذلك. الافتراضيّ سماح (حين
    تكون الراية العامّة مُفعَّلة) — فالمنع الصريح للمستأجِر يُحترَم دائماً."""
    p = policy or {}
    if p.get("ai_generation") == "deny":
        return False
    if p.get("ai_generation_allowed") is False:
        return False
    return True


def _normalize_provider(raw: str | None) -> str:
    p = (raw or "").strip().lower()
    if p in {"anthropic", "claude", "cloud"}:
        return "anthropic"
    if p in {"openrouter", "router", "or"}:
        return "openrouter"
    return "local"


def _catalog_ids() -> set[str]:
    raw = (os.getenv("AI_MODELS") or "").strip()
    ids: set[str] = set()
    for entry in raw.split(","):
        mid = entry.partition("|")[0].strip()
        if mid:
            ids.add(mid)
    return ids


def _resolve_model(shared_model: str, requested: str | None) -> str:
    allowed = _catalog_ids()
    req = (requested or "").strip()
    if req and (not allowed or req in allowed):
        return req
    return shared_model


@dataclass(frozen=True)
class GenConfig:
    provider: str
    endpoint: str
    headers: dict[str, str]
    model: str
    wire_format: str  # 'openai_chat' | 'messages'


@dataclass(frozen=True)
class GenResult:
    text: str
    model: str
    provider: str


def resolve_generation(requested_model: str | None = None) -> GenConfig | None:
    """يحلّ مزوّد التوليد من البيئة. يعيد ``None`` إن لم يكن مزوّد سحابيّ جاهزاً
    (مفتاح/نموذج) — إشارةً للمستدعي بالسقوط إلى الأدلّة. المحلّيّ (Ollama) متاح بلا
    مفتاح لكن قد يفشل وقت الاستدعاء (يُعالَج بالسقوط الآمن)."""
    provider = _normalize_provider(os.getenv("AI_PROVIDER"))
    shared_model = (os.getenv("AI_MODEL") or "").strip()

    if provider == "openrouter":
        api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        model = _resolve_model(shared_model, requested_model)
        if not api_key or not model:
            return None
        base = (os.getenv("OPENROUTER_BASE_URL") or DEFAULT_OPENROUTER_BASE_URL).strip()
        headers = {"content-type": "application/json", "authorization": f"Bearer {api_key}"}
        title = (os.getenv("OPENROUTER_APP_TITLE") or "SAHOOL").strip()
        if title:
            headers["x-title"] = title
        return GenConfig(
            "openrouter", f"{base.rstrip('/')}/chat/completions", headers, model, "openai_chat"
        )

    if provider == "anthropic":
        api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        model = _resolve_model(
            shared_model or (os.getenv("ANTHROPIC_MODEL") or "").strip(), requested_model
        )
        if not api_key or not model:
            return None
        base = (os.getenv("ANTHROPIC_BASE_URL") or DEFAULT_ANTHROPIC_BASE_URL).strip()
        headers = {
            "content-type": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
            "x-api-key": api_key,
        }
        return GenConfig("anthropic", f"{base.rstrip('/')}/v1/messages", headers, model, "messages")

    # المحلّيّ (Ollama، Anthropic-compatible) — لا مفتاح؛ يُولّد إن كان مُشغَّلاً.
    model = _resolve_model(
        shared_model or (os.getenv("LOCAL_LLM_MODEL") or "qwen3").strip(), requested_model
    )
    if not model:
        return None
    base = (os.getenv("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL).strip()
    token = (os.getenv("OLLAMA_API_KEY") or "ollama").strip()
    headers = {
        "content-type": "application/json",
        "anthropic-version": ANTHROPIC_VERSION,
        "authorization": f"Bearer {token}",
    }
    return GenConfig("local", f"{base.rstrip('/')}/v1/messages", headers, model, "messages")


def _build_payload(cfg: GenConfig, question: str, context_text: str, max_tokens: int) -> dict:
    user = f"الأدلّة:\n{context_text}\n\nالسؤال: {question}"
    if cfg.wire_format == "openai_chat":
        return {
            "model": cfg.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": _GROUNDED_SYSTEM_AR},
                {"role": "user", "content": user},
            ],
        }
    return {
        "model": cfg.model,
        "max_tokens": max_tokens,
        "system": _GROUNDED_SYSTEM_AR,
        "messages": [{"role": "user", "content": user}],
    }


def _extract_text(cfg: GenConfig, data: dict) -> str:
    """يستخرج النصّ حسب صيغة السلك؛ بنية غير متوقّعة ⇒ نصّ فارغ (يسقط المستدعي)."""
    try:
        if cfg.wire_format == "openai_chat":
            return (data["choices"][0]["message"]["content"] or "").strip()
        # Anthropic messages: content = [{type:text, text:...}, ...]
        parts = data.get("content") or []
        return "".join(b.get("text", "") for b in parts if b.get("type") == "text").strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""


async def generate(
    question: str,
    context_text: str,
    requested_model: str | None = None,
    *,
    max_tokens: int = 600,
    timeout: float = 20.0,
) -> GenResult | None:
    """يولّد جواباً مؤرَّضاً أو يعيد ``None`` (للسقوط الآمن إلى الأدلّة). لا يرفع
    استثناءً للمستدعي مهما فشل المزوّد."""
    if not generation_enabled():
        return None
    cfg = resolve_generation(requested_model)
    if cfg is None:
        return None
    payload = _build_payload(cfg, question, context_text, max_tokens)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(cfg.endpoint, headers=cfg.headers, json=payload)
        if resp.status_code >= 400:
            logger.warning("توليد %s فشل: HTTP %s", cfg.provider, resp.status_code)
            return None
        text = _extract_text(cfg, resp.json())
    except Exception as e:  # noqa: BLE001 — أيّ فشل ⇒ سقوط آمن إلى الأدلّة
        logger.warning("تعذّر التوليد عبر %s: %s", cfg.provider, type(e).__name__)
        return None
    if not text:
        return None
    return GenResult(text=text, model=cfg.model, provider=cfg.provider)
