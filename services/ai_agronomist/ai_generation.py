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

import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from shared.ai import tool_schema as agent_tool_schema

try:  # package import in service runtime / pytest normal path
    from . import tool_loop
except ImportError:  # direct spec import used by legacy unit guards
    from services.ai_agronomist import tool_loop  # type: ignore

logger = logging.getLogger("ai_agronomist.generation")

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_OLLAMA_BASE_URL = "http://sahool-ollama:11434"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_VLLM_BASE_URL = "http://sahool-vllm-jais:8000/v1"
DEFAULT_VLLM_MODEL = "jais-natural-farmer"

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
    "local": [("llama3.2:3b", "Llama 3.2 3B (محلّيّ / Ollama)")],
    "vllm": [("jais-natural-farmer", "Jais Natural Farmer (Solshine / vLLM)")],
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
    if p in {"vllm", "jais", "jais-natural-farmer"}:
        return "vllm"
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
        else ("messages" if provider == "anthropic" else "openai_chat"),
        "models": public_model_catalog(provider),
        "data_sharing_modes": ["local_only", "redacted_external", "full_external"],
    }


def _catalog_ids(provider: str) -> set[str]:
    """معرّفات النماذج المسموحة للمزوّد — من ``AI_MODELS`` **أو الكتالوج الافتراضيّ**.

    fail-closed: لا تعود فارغةً لمزوّد معروف حين يغيب ``AI_MODELS`` — فيبقى النموذج المطلوب
    محكوماً بقائمة سماح فعليّة (يسدّ تجاوز allowlist H-AI-1).
    """
    return {m["id"] for m in public_model_catalog(provider)}


def _resolve_model(provider: str, shared_model: str, requested: str | None) -> str:
    """يحلّ النموذج **fail-closed**: النموذج المطلوب (من الواجهة/المستخدم) يُقبَل **فقط** إن
    كان ضمن كتالوج المزوّد الفعليّ (``AI_MODELS`` أو الافتراضيّ) — **لا تجاوز لقائمة السماح
    حتّى حين غياب ``AI_MODELS``**. خلافه ⇒ ``shared_model`` المضبوط بيئيّاً (الافتراضيّ الموثوق)."""
    allowed = _catalog_ids(provider)
    req = (requested or "").strip()
    if req and req in allowed:
        return req
    if shared_model and (not allowed or shared_model in allowed):
        return shared_model
    catalog = public_model_catalog(provider)
    return catalog[0]["id"] if catalog else ""


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
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    tool_calls_truncated: bool = False
    tool_rounds: int = 0
    stop_reason: str | None = None
    incomplete: bool = False


def resolve_generation(requested_model: str | None = None) -> GenConfig | None:
    """يحلّ مزوّد التوليد من البيئة. يعيد ``None`` إن لم يكن مزوّد سحابيّ جاهزاً
    (مفتاح/نموذج) — إشارةً للمستدعي بالسقوط إلى الأدلّة. المحلّيّ (Ollama) متاح بلا
    مفتاح لكن قد يفشل وقت الاستدعاء (يُعالَج بالسقوط الآمن)."""
    provider = _normalize_provider(os.getenv("AI_PROVIDER"))
    shared_model = (os.getenv("AI_MODEL") or "").strip()

    if provider == "vllm":
        model = _resolve_model(
            "vllm",
            shared_model or (os.getenv("VLLM_MODEL") or DEFAULT_VLLM_MODEL).strip(),
            requested_model,
        )
        if not model:
            return None
        base = (os.getenv("VLLM_BASE_URL") or DEFAULT_VLLM_BASE_URL).strip()
        token = (os.getenv("VLLM_API_KEY") or "sahool-vllm-local").strip()
        headers = {"content-type": "application/json"}
        if token:
            headers["authorization"] = f"Bearer {token}"
        return GenConfig(
            "vllm", f"{base.rstrip('/')}/chat/completions", headers, model, "openai_chat"
        )

    if provider == "openrouter":
        api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        model = _resolve_model("openrouter", shared_model, requested_model)
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
            "anthropic",
            shared_model or (os.getenv("ANTHROPIC_MODEL") or "").strip(),
            requested_model,
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

    # المحلّيّ (Ollama) عبر OpenAI-compatible Chat Completions.
    model = _resolve_model(
        "local",
        shared_model or (os.getenv("LOCAL_LLM_MODEL") or "llama3.2:3b").strip(),
        requested_model,
    )
    if not model:
        return None
    base = (os.getenv("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL).strip()
    token = (os.getenv("OLLAMA_API_KEY") or "ollama").strip()
    headers = {"content-type": "application/json", "authorization": f"Bearer {token}"}
    return GenConfig(
        "local", f"{base.rstrip('/')}/v1/chat/completions", headers, model, "openai_chat"
    )


def _provider_tools(cfg: GenConfig, allowed_capabilities: list[str] | None) -> list[dict[str, Any]]:
    # Jais Natural Farmer is a grounded-generation provider. Tool calls stay opt-in
    # until model-specific tool-call conformance is proven; no direct actions by default.
    if cfg.provider == "vllm" and (
        os.getenv("VLLM_ENABLE_TOOLS") or "false"
    ).strip().lower() not in {"1", "true", "yes", "on"}:
        return []
    """Provider-native tool schema, filtered by tenant capabilities before the model sees it."""
    defs = agent_tool_schema.tool_definitions(allowed_capabilities)
    if cfg.wire_format == "openai_chat":
        return [
            {
                "type": "function",
                "function": {
                    "name": d["name"],
                    "description": d["description"],
                    "parameters": d["parameters"],
                },
            }
            for d in defs
        ]
    return [
        {
            "name": d["name"],
            "description": d["description"],
            "input_schema": d["parameters"],
        }
        for d in defs
    ]


def _compact_tool_result(item: dict[str, Any]) -> dict[str, Any]:
    """نتيجة أداة مختصرة تصلح لإرجاعها للمزوّد كتغذية tool_result."""
    return {
        "tool": item.get("tool"),
        "outcome": item.get("outcome"),
        "risk": item.get("risk"),
        "reason": item.get("reason"),
        "requires_approval": item.get("requires_approval"),
        "approval_id": item.get("approval_id"),
        "data": item.get("data"),
    }


def _tool_result_text(results: list[dict[str, Any]] | None) -> str:
    compact = [_compact_tool_result(r) for r in (results or [])[:8] if isinstance(r, dict)]
    return json.dumps(compact, ensure_ascii=False, sort_keys=True, default=str)


def _base_user_text(question: str, context_text: str) -> str:
    return f"الأدلّة:\n{context_text}\n\nالسؤال: {question}"


def _build_payload(
    cfg: GenConfig,
    question: str,
    context_text: str,
    max_tokens: int,
    *,
    tools: list[dict[str, Any]] | None = None,
    tool_results: list[dict[str, Any]] | None = None,
) -> dict:
    """يبني الحمولة الأولى أو حمولة fallback نصيّة لنتائج الأدوات.

    الإرجاع native tool_result يتم عبر ``_build_native_tool_result_payload``؛ هذه الدالة
    باقية للحراس القديمة وللسقوط الآمن إن لم تقبل صيغة مزوّد ما."""
    tool_tail = ""
    if tool_results:
        tool_tail = f"\n\nنتائج أدوات الـHarness:\n{_tool_result_text(tool_results)}"
    user = f"الأدلّة:\n{context_text}{tool_tail}\n\nالسؤال: {question}"
    if cfg.wire_format == "openai_chat":
        payload = {
            "model": cfg.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": _GROUNDED_SYSTEM_AR},
                {"role": "user", "content": user},
            ],
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload
    payload = {
        "model": cfg.model,
        "max_tokens": max_tokens,
        "system": _GROUNDED_SYSTEM_AR,
        "messages": [{"role": "user", "content": user}],
    }
    if tools:
        payload["tools"] = tools
    return payload


def _arguments_for_tool_call(call: dict[str, Any]) -> str:
    return json.dumps(
        call.get("params") if isinstance(call.get("params"), dict) else {},
        ensure_ascii=False,
        sort_keys=True,
    )


def _build_native_tool_result_payload(
    cfg: GenConfig,
    question: str,
    context_text: str,
    max_tokens: int,
    *,
    provider_calls: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """يرجع نتائج الأدوات للمزوّد بصيغته الأصلية: OpenAI tool messages أو Anthropic tool_result."""
    if cfg.wire_format == "openai_chat":
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _GROUNDED_SYSTEM_AR},
            {
                "role": "user",
                "content": _base_user_text(question, context_text)
                + "\n\nنتائج أدوات الـHarness: تُرفَق كرسائل tool_result أصلية أدناه.",
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": str(c.get("id") or c.get("tool_call_id") or f"call-{i}"),
                        "type": "function",
                        "function": {
                            "name": c.get("tool"),
                            "arguments": _arguments_for_tool_call(c),
                        },
                    }
                    for i, c in enumerate(provider_calls)
                ],
            },
        ]
        for i, result in enumerate(tool_results):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(
                        result.get("tool_call_id") or result.get("id") or f"call-{i}"
                    ),
                    "name": str(result.get("tool") or "tool"),
                    "content": json.dumps(
                        _compact_tool_result(result),
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ),
                }
            )
        payload: dict[str, Any] = {
            "model": cfg.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    assistant_content = [
        {
            "type": "tool_use",
            "id": str(c.get("id") or c.get("tool_call_id") or f"toolu-{i}"),
            "name": str(c.get("tool") or ""),
            "input": c.get("params") if isinstance(c.get("params"), dict) else {},
        }
        for i, c in enumerate(provider_calls)
    ]
    result_blocks = [
        {
            "type": "tool_result",
            "tool_use_id": str(r.get("tool_call_id") or r.get("id") or f"toolu-{i}"),
            "content": json.dumps(
                _compact_tool_result(r), ensure_ascii=False, sort_keys=True, default=str
            ),
            "is_error": r.get("outcome") not in {"executed", "pending_approval"},
        }
        for i, r in enumerate(tool_results)
    ]
    payload = {
        "model": cfg.model,
        "max_tokens": max_tokens,
        "system": _GROUNDED_SYSTEM_AR,
        "messages": [
            {"role": "user", "content": _base_user_text(question, context_text)},
            {"role": "assistant", "content": assistant_content},
            {"role": "user", "content": result_blocks},
        ],
    }
    if tools:
        payload["tools"] = tools
    return payload


def _extract_provider_tool_calls(cfg: GenConfig, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse provider-native tool calls into SAHOOL's internal {tool, params, id} shape."""
    calls: list[dict[str, Any]] = []
    try:
        if cfg.wire_format == "openai_chat":
            raw_calls = data["choices"][0].get("message", {}).get("tool_calls") or []
            for raw in raw_calls:
                fn = (raw or {}).get("function") or {}
                name = str(fn.get("name") or "")
                if not name:
                    continue
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args or "{}")
                    except Exception:
                        args = {}
                calls.append(
                    {
                        "id": raw.get("id"),
                        "tool": name,
                        "params": args if isinstance(args, dict) else {},
                    }
                )
            return calls
        for block in data.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls.append(
                    {
                        "id": block.get("id"),
                        "tool": str(block.get("name") or ""),
                        "params": block.get("input")
                        if isinstance(block.get("input"), dict)
                        else {},
                    }
                )
    except Exception:
        return []
    return [c for c in calls if c.get("tool")]


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


def _extract_stop_reason(cfg: GenConfig, data: dict[str, Any]) -> str | None:
    """Normalize provider finish/stop reason for audit-safe control flow."""
    try:
        if cfg.wire_format == "openai_chat":
            choice = (data.get("choices") or [{}])[0]
            return choice.get("finish_reason") or choice.get("stop_reason")
        return data.get("stop_reason")
    except Exception:  # noqa: BLE001 — قراءة سبب التوقّف اختياريّة؛ أيّ شكل رد غير متوقّع ⇒ None بأمان
        return None


def _stop_reason_is_incomplete(reason: str | None) -> bool:
    return str(reason or "").strip().lower() in {
        "length",
        "max_tokens",
        "model_context_window_exceeded",
        "content_filter",
        "refusal",
    }


async def generate(
    question: str,
    context_text: str,
    requested_model: str | None = None,
    *,
    policy: dict[str, Any] | None = None,
    allowed_capabilities: list[str] | None = None,
    tool_fetcher: Callable[[str, dict[str, Any]], Any] | None = None,
    tenant_id: str | None = None,
    actor: str = "ai_agronomist",
    timestamp: str | None = None,
    max_tool_rounds: int = 1,
    max_tokens: int = 600,
    audit_saver: tool_loop.AuditSaver | None = None,
    approval_saver: tool_loop.ApprovalSaver | None = None,
    allowed_tools: set[str] | None = None,
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
    tool_results: list[dict[str, Any]] = []
    pending_approvals: list[dict[str, Any]] = []
    truncated = False
    rounds = 0
    # V58.2c — run-level abuse protection shared across every tool round of this generation.
    dedupe_seen: set[str] = set()
    run_spent = 0
    run_budget = tool_loop.DEFAULT_RUN_TOOL_BUDGET
    max_rounds = max(0, min(int(max_tool_rounds or 0), 5))
    tools = _provider_tools(cfg, allowed_capabilities) if max_rounds > 0 else []
    payload = _build_payload(cfg, question, context_text, max_tokens, tools=tools)
    text = ""
    stop_reason: str | None = None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(cfg.endpoint, headers=cfg.headers, json=payload)
            if resp.status_code >= 400:
                logger.warning("توليد %s فشل: HTTP %s", cfg.provider, resp.status_code)
                return None
            data = resp.json()
            stop_reason = _extract_stop_reason(cfg, data)

            while True:
                provider_calls = _extract_provider_tool_calls(cfg, data)
                if (
                    not provider_calls
                    or tool_fetcher is None
                    or not tenant_id
                    or rounds >= max_rounds
                ):
                    text = _extract_text(cfg, data)
                    break

                loop_out = tool_loop.run_tool_calls(
                    provider_calls,
                    allowed_capabilities=allowed_capabilities,
                    fetcher=tool_fetcher,
                    tenant_id=tenant_id,
                    actor=actor,
                    timestamp=timestamp or "provider-native",
                    provider=cfg.provider,
                    model=cfg.model,
                    audit_saver=audit_saver,
                    approval_saver=approval_saver,
                    run_budget=run_budget,
                    run_spent=run_spent,
                    dedupe_seen=dedupe_seen,
                    stop_on_pending=True,
                    allowed_tools=allowed_tools,
                )
                batch_results = list(loop_out.get("tool_calls") or [])
                tool_results.extend(batch_results)
                pending_approvals.extend(list(loop_out.get("pending_approvals") or []))
                truncated = truncated or bool(loop_out.get("truncated"))
                run_spent += int(loop_out.get("handled_count") or 0)
                rounds += 1

                # إن وصلت أدوات تحتاج موافقة، نعيدها للمزوّد كـ tool_result ثم نمنع أدوات إضافية
                # كي يُكمل جواباً يشرح أن التنفيذ بانتظار الإنسان. V58.2c — كذلك نمنع أدوات إضافية
                # عند نفاد ميزانية الأدوات لهذا الـrun (يُكمل النموذج نصّاً على النتائج المتاحة).
                budget_left = run_spent < run_budget
                next_tools = (
                    tools if rounds < max_rounds and not pending_approvals and budget_left else None
                )
                payload = _build_native_tool_result_payload(
                    cfg,
                    question,
                    context_text,
                    max_tokens,
                    provider_calls=provider_calls,
                    tool_results=batch_results,
                    tools=next_tools,
                )
                resp = await client.post(cfg.endpoint, headers=cfg.headers, json=payload)
                if resp.status_code >= 400:
                    logger.warning(
                        "توليد %s بعد الأدوات فشل: HTTP %s", cfg.provider, resp.status_code
                    )
                    # سقوط نصي متوافق مع الحراس القديمة/المزوّدات غير المكتملة.
                    fallback_payload = _build_payload(
                        cfg,
                        question,
                        context_text,
                        max_tokens,
                        tools=None,
                        tool_results=tool_results,
                    )
                    resp = await client.post(
                        cfg.endpoint, headers=cfg.headers, json=fallback_payload
                    )
                    if resp.status_code >= 400:
                        text = _extract_text(cfg, data)
                        break
                data = resp.json()
                stop_reason = _extract_stop_reason(cfg, data)

            if not text:
                text = _extract_text(cfg, data)
    except Exception as e:  # noqa: BLE001 — أيّ فشل ⇒ سقوط آمن إلى الأدلّة
        logger.warning("تعذّر التوليد عبر %s: %s", cfg.provider, type(e).__name__)
        return None
    if not text:
        return None
    incomplete = _stop_reason_is_incomplete(stop_reason)
    if incomplete:
        text = (
            text
            + "\n\nتنبيه: أوقف المزوّد الاستجابة قبل اكتمالها؛ راجع الأدلة أو أعد الطلب بنطاق أضيق."
        )
    return GenResult(
        text=text,
        model=cfg.model,
        provider=cfg.provider,
        tool_calls=tool_results,
        pending_approvals=pending_approvals,
        tool_calls_truncated=truncated,
        tool_rounds=rounds,
        stop_reason=stop_reason,
        incomplete=incomplete,
    )
