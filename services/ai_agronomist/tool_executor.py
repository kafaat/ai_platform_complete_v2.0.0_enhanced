"""منفّذ أدوات الوكيل (V55 — المرحلة ٢: بوّابة الحوكمة + تنفيذ القراءة).

النموذج يطلب أداة؛ هذا المنفّذ **يقرّر قبل التنفيذ** بناءً على قدرات المستأجِر وخطورة
الأداة، ثمّ يُنفّذ أدوات القراءة فقط:

- أداة مجهولة ⇒ ``denied`` (fail-closed).
- قدرة مطلوبة غير ممنوحة ⇒ ``denied``.
- أداة مُعدِّلة/عالية الخطورة ⇒ ``pending_approval`` (لا تُنفَّذ هنا؛ تنتظر موافقة
  بشريّة — المرحلة ٤). لا أثر جانبيّ في هذه المرحلة.
- أداة قراءة + قدرة ممنوحة ⇒ تُنفَّذ عبر ``fetcher`` محقون (لا خدمات حيّة في الاختبار؛
  الإنتاج يصل عملاء HTTP الفعليّين). فشل الجالب ⇒ ``failed`` بلا رفع استثناء للمستدعي.

``_TOOL_META`` مرآة ``shared/ai/tool_registry`` (يفرض التطابقَ حارس
``tests_v9/test_ai_tool_executor_v55.py``؛ الكود معزول لكلّ خدمة، العقد مشترك).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from typing import Any

logger = logging.getLogger("ai_agronomist.tool_executor")

# القدرات القرائيّة الممنوحة افتراضيّاً (fail-closed) — مرآة
# ``tenant_policies.DEFAULT_AGENT_CAPABILITIES`` / ``shared.ai.capabilities``.
_DEFAULT_CAPABILITIES = ("can_read_field_data", "can_read_historical_imagery")


def _granted(allowed: Iterable[str] | None) -> set[str]:
    """القدرات الفعّالة: ``None`` ⇒ الافتراضيّ القرائيّ المتحفّظ؛ وإلّا ما مُنِح
    (نصّاً مُطبَّعاً). القيمة المجهولة لا تمنح شيئاً (لن تطابق قدرة أداة)."""
    if allowed is None:
        return set(_DEFAULT_CAPABILITIES)
    return {str(c).strip().lower() for c in allowed}


# نتائج قانونيّة (مرآة ``shared/ai/tool_audit.OUTCOMES``).
OUTCOME_EXECUTED = "executed"
OUTCOME_PENDING_APPROVAL = "pending_approval"
OUTCOME_DENIED = "denied"
OUTCOME_FAILED = "failed"

# قرار البوّابة (قبل التنفيذ).
DECISION_ALLOWED = "allowed"

# مرآة سجلّ الأدوات: name -> (capability, risk, mutating, requires_approval).
_TOOL_META: dict[str, tuple[str, str, bool, bool]] = {
    "get_field_state": ("can_read_field_data", "low", False, False),
    "get_truecolor_scene": ("can_read_historical_imagery", "low", False, False),
    "get_index_timeline": ("can_read_historical_imagery", "low", False, False),
    "get_weather_history": ("can_read_field_data", "low", False, False),
    "get_operation_windows": ("can_read_field_data", "low", False, False),
    "get_alerts": ("can_read_field_data", "low", False, False),
    "get_drawings_and_zones": ("can_read_field_data", "low", False, False),
    "open_map_layer": ("can_read_field_data", "low", False, False),
    "create_scouting_task": ("can_create_tasks", "medium", True, False),
    "request_imagery_backfill": ("can_trigger_backfill", "medium", True, False),
    "draft_recommendation": ("can_send_recommendations", "medium", True, False),
    "send_recommendation": ("can_send_recommendations", "high", True, True),
    "create_prescription_map": ("can_generate_prescriptions", "high", True, True),
    "schedule_irrigation": ("can_send_recommendations", "high", True, True),
    "export_enterprise_data": ("can_export_enterprise_data", "high", True, True),
}

_SECRET_HINTS = ("token", "secret", "api_key", "apikey", "password", "authorization")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# جالب أداة: (tool_name, params) -> بيانات القراءة. يُحقَن (لا خدمات حيّة في الاختبار).
ToolFetcher = Callable[[str, "dict[str, Any]"], Any]


def _redact(params: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (params or {}).items():
        if any(h in str(key).strip().lower() for h in _SECRET_HINTS):
            out[key] = "[redacted]"
        elif isinstance(value, str):
            out[key] = _UUID_RE.sub("[redacted-id]", _EMAIL_RE.sub("[redacted-email]", value))
        else:
            out[key] = value
    return out


def plan_tool_call(
    tool_name: str, params: dict[str, Any] | None, allowed_capabilities
) -> dict[str, Any]:
    """قرار البوّابة قبل التنفيذ (بلا أثر جانبيّ). fail-closed للمجهول/الناقص."""
    meta = _TOOL_META.get(tool_name)
    if meta is None:
        return {
            "outcome": OUTCOME_DENIED,
            "reason": "unknown_tool",
            "capability": None,
            "risk": "high",
            "requires_approval": True,
        }
    capability, risk, mutating, requires_approval = meta
    base = {"capability": capability, "risk": risk, "requires_approval": requires_approval}
    if capability not in _granted(allowed_capabilities):
        return {"outcome": OUTCOME_DENIED, "reason": "capability_not_granted", **base}
    if mutating or requires_approval:
        reason = "needs_human_approval" if requires_approval else "mutating_deferred"
        return {"outcome": OUTCOME_PENDING_APPROVAL, "reason": reason, **base}
    return {"outcome": DECISION_ALLOWED, "reason": "read_allowed", **base}


def execute_read_tool(
    tool_name: str,
    params: dict[str, Any] | None,
    allowed_capabilities,
    fetcher: ToolFetcher | None,
    *,
    tenant_id: str,
    actor: str,
    timestamp: str,
) -> dict[str, Any]:
    """يُنفّذ أداة قراءة بعد بوّابة الحوكمة، ويُرجِع نتيجةً تحمل سجلّ تدقيق.

    لا يُنفّذ أدوات مُعدِّلة/عالية (تُرجَع ``pending_approval``). ``timestamp`` يُمرَّر
    من الخارج (حتميّ). لا يرفع استثناءً للمستدعي مهما فشل الجالب."""
    plan = plan_tool_call(tool_name, params, allowed_capabilities)
    outcome = plan["outcome"]
    data: Any = None
    reason = plan["reason"]

    if outcome == DECISION_ALLOWED:
        if fetcher is None:
            outcome, reason = OUTCOME_FAILED, "no_fetcher"
        else:
            try:
                data = fetcher(tool_name, params or {})
                outcome = OUTCOME_EXECUTED
            except Exception as exc:  # سقوط آمن — لا استثناء للمستدعي.
                logger.warning("فشل جالب الأداة %s: %s", tool_name, exc)
                outcome, reason = OUTCOME_FAILED, "fetcher_error"

    return {
        "tool": tool_name,
        "outcome": outcome,
        "reason": reason,
        "risk": plan["risk"],
        "capability": plan["capability"],
        "requires_approval": plan["requires_approval"],
        "data": data,
        "audit": {
            "tool": tool_name,
            "params": _redact(params),
            "tenant_id": str(tenant_id),
            "actor": str(actor),
            "outcome": outcome,
            "risk": plan["risk"],
            "capability": plan["capability"],
            "timestamp": timestamp,
        },
    }
