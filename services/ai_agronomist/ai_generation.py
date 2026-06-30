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
import re
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("ai_agronomist.generation")

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_OLLAMA_BASE_URL = "http://ollama:11434"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# المزوّدات الخارجيّة (سحابيّة) — تخضع لسياسة مشاركة البيانات/التنقيح.
# (مرآة ``shared/ai/provider_contract.EXTERNAL_PROVIDERS`` — يفرض التطابقَ الحارس.)
_EXTERNAL_PROVIDERS = ("anthropic", "openrouter")

# كتالوج النماذج الافتراضيّ — مرآة ``shared/ai/provider_contract.DEFAULT_CATALOG``
# و``ai_provider_config._DEFAULT_CATALOG`` (يفرض التطابقَ حارس عقد المزوّد).
_DEFAULT_CATALOG: dict[str, list[tuple[str, str]]] = {
    "openrouter": [
        ("deepseek/deepseek-chat", "DeepSeek"),
        ("anthropic/claude-sonnet-4.6", "Claude Sonnet"),
        ("google/gemini-3-pro", "Gemini 3 Pro"),
    ],
    "local": [
        ("qwen3", "Qwen3 (محلّيّ)"),
        ("qwen3:32b", "Qwen3 32B (محلّيّ)"),
    ],
}

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


# ──────────────────────────────────────────────────────────────────────────
# إنفاذ سياسة مشاركة البيانات (V52) — قبل إرسال أيّ سياق حقل لمزوّد خارجيّ.
# ──────────────────────────────────────────────────────────────────────────
def _policy_mode(policy: dict[str, Any] | None) -> str:
    """مستوى مشاركة البيانات من سياسة المستأجِر (المفتاح القانونيّ ``data_sharing_level``
    مع توافق رجعيّ لـ``data_sharing``). الافتراضيّ المتحفّظ ``local_only``."""
    p = policy or {}
    raw = p.get("data_sharing_level") or p.get("data_sharing") or "local_only"
    mode = str(raw).strip().lower()
    return mode if mode in {"local_only", "redacted_external", "full_external"} else "local_only"


def provider_is_external(provider: str | None) -> bool:
    return (provider or "").strip().lower() in _EXTERNAL_PROVIDERS


def redact_context_for_external(context_text: str) -> str:
    """يُقلّل معرّفات المستأجِر/الحقل قبل إرسال الأدلّة لنموذج سحابيّ.

    طبقة أمان إضافيّة (لا بديل عن السياسة) للمستأجرين الذين يسمحون صراحةً بالتوليد
    الخارجيّ المُنقَّح: يُخفي البريد/المعرّفات الكونيّة/الأرقام الطويلة/الإحداثيّات،
    ويحدّ طول الإرسال."""
    text = context_text or ""
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted-email]", text)
    text = re.sub(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        "[redacted-id]",
        text,
    )
    text = re.sub(r"(?<!\d)(?:\+?\d[\d .()/-]{7,}\d)(?!\d)", "[redacted-number]", text)
    text = re.sub(
        r"(?<!\d)([-+]?\d{1,2}\.\d{4,})\s*,\s*([-+]?\d{1,3}\.\d{4,})(?!\d)",
        "[redacted-coordinates]",
        text,
    )
    return text[:6000]


def prepare_context_for_provider(
    cfg: GenConfig, context_text: str, policy: dict[str, Any] | None
) -> str | None:
    """يُنفِّذ سياسة مشاركة البيانات على السياق قبل إرساله للمزوّد.

    - مزوّد محلّيّ ⇒ يمرّ السياق كما هو (لا يغادر الحدّ).
    - مزوّد خارجيّ + ``local_only`` ⇒ ``None`` (يُحجَب التوليد الخارجيّ ⇒ سقوط آمن).
    - ``redacted_external`` ⇒ سياق مُنقَّح. ``full_external`` ⇒ سياق كامل."""
    if not provider_is_external(cfg.provider):
        return context_text
    mode = _policy_mode(policy)
    if mode == "redacted_external":
        return redact_context_for_external(context_text)
    if mode == "full_external":
        return context_text
    return None  # local_only (أو مجهول) ⇒ لا تُرسَل بيانات الحقل خارجيّاً


def public_model_catalog(provider: str | None = None) -> list[dict[str, str]]:
    """قائمة النماذج المتاحة (للقطة المزوّد/الواجهة) — بلا أسرار."""
    prov = _normalize_provider(provider or os.getenv("AI_PROVIDER"))
    raw = (os.getenv("AI_MODELS") or "").strip()
    items: list[dict[str, str]] = []
    if raw:
        for entry in raw.split(","):
            mid, _, label = entry.partition("|")
            mid = mid.strip()
            if mid:
                items.append({"id": mid, "label": label.strip() or mid})
    if not items:
        items = [{"id": mid, "label": label} for mid, label in _DEFAULT_CATALOG.get(prov, [])]
    return items


def public_provider_snapshot(requested_model: str | None = None) -> dict[str, Any]:
    """إسقاط رصديّ آمن (بلا أسرار) لحالة المزوّد — لنقطة اللقطة/الإدارة. يُغلِق توصية
    تدقيق V51 (لقطة مزوّد واحدة يستهلكها الـruntime/الواجهة)."""
    provider = _normalize_provider(os.getenv("AI_PROVIDER"))
    cfg = resolve_generation(requested_model)
    return {
        "generation_enabled": generation_enabled(),
        "provider": provider,
        "provider_class": "external" if provider_is_external(provider) else "local",
        "available": cfg is not None,
        "model": cfg.model if cfg else None,
        "wire_format": cfg.wire_format
        if cfg
        else ("openai_chat" if provider == "openrouter" else "messages"),
        "models": public_model_catalog(provider),
        "data_sharing_modes": ["local_only", "redacted_external", "full_external"],
    }


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
    policy: dict[str, Any] | None = None,
    max_tokens: int = 600,
    timeout: float = 20.0,
) -> GenResult | None:
    """يولّد جواباً مؤرَّضاً أو يعيد ``None`` (للسقوط الآمن إلى الأدلّة). لا يرفع
    استثناءً للمستدعي مهما فشل المزوّد.

    يُنفِّذ سياسة مشاركة بيانات المستأجِر (``policy``) قبل الإرسال: مزوّد خارجيّ مع
    ``local_only`` يُحجَب (⇒ ``None``)، ``redacted_external`` يُرسَل سياقاً مُنقَّحاً."""
    if not generation_enabled():
        return None
    cfg = resolve_generation(requested_model)
    if cfg is None:
        return None
    prepared = prepare_context_for_provider(cfg, context_text, policy)
    if prepared is None:
        logger.info(
            "حُجِب التوليد الخارجيّ (%s) بسياسة مشاركة بيانات المستأجِر — سقوط إلى الأدلّة.",
            cfg.provider,
        )
        return None
    context_text = prepared
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
