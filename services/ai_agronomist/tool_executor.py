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

import json
import logging
import re
from collections.abc import Callable, Iterable
from datetime import date, timedelta
from typing import Any

try:
    from .approval import input_hash, summarize_result
except ImportError:  # direct spec import used by legacy unit guards
    from services.ai_agronomist.approval import input_hash, summarize_result  # type: ignore

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
    "get_water_productivity": ("can_read_field_data", "low", False, False),
    "generate_report": ("can_read_field_data", "low", False, False),
    "get_operation_windows": ("can_read_field_data", "low", False, False),
    "get_alerts": ("can_read_field_data", "low", False, False),
    "get_drawings_and_zones": ("can_read_field_data", "low", False, False),
    "open_map_layer": ("can_read_field_data", "low", False, False),
    "detect_field_boundaries": ("can_read_historical_imagery", "low", False, False),
    "generate_productivity_zones": ("can_read_historical_imagery", "low", False, False),
    "plan_soil_sampling": ("can_read_historical_imagery", "low", False, False),
    "generate_vra_prescription": ("can_read_historical_imagery", "low", False, False),
    "create_scouting_task": ("can_create_tasks", "medium", True, True),
    "request_imagery_backfill": ("can_trigger_backfill", "medium", True, True),
    "draft_recommendation": ("can_send_recommendations", "medium", True, True),
    "save_detected_boundary": ("can_manage_field_boundaries", "high", True, True),
    "save_productivity_zones": ("can_manage_productivity_zones", "high", True, True),
    "save_soil_sampling_plan": ("can_manage_soil_sampling", "high", True, True),
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


def _audit_summary(data: Any) -> str:
    """A read that answered "not available" is audited as such, with its reason."""
    if isinstance(data, dict) and data.get("available") is False and data.get("reason"):
        return f"unavailable:{data['reason']}"[:240]
    return summarize_result(data)


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

    candidate = None
    if plan["outcome"] == OUTCOME_PENDING_APPROVAL:
        candidate = {
            "kind": "agent_action_candidate.v1",
            "tool": tool_name,
            "params": _redact(params),
            "tenant_id": str(tenant_id),
            "actor": str(actor),
            "requested_at": timestamp,
            "input_hash": input_hash(params),
            "authority": "decision_service",
            "required_chain": [
                "candidate",
                "decision",
                "approval",
                "execution",
                "evidence",
                "outcome",
            ],
            "direct_action_permitted": False,
        }
    return {
        "tool": tool_name,
        "outcome": outcome,
        "candidate": candidate,
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
            "input_hash": input_hash(params),
            "result_summary": _audit_summary(data if outcome == OUTCOME_EXECUTED else reason),
            "result": data if outcome == OUTCOME_EXECUTED else {"reason": reason},
        },
    }


# ── F4: read answers cut to the arguments the model passed ─────────────────────────────
# The read tools serve one already-loaded AI context pack and do not call the owners
# again. Each answer below is either exactly the requested slice of the owner's block
# (one index, one window, one scene date), or ``available: False`` with a ``reason`` code
# and an Arabic note. A block is never returned whole next to the caller's arguments: that
# made a 730-day bundle read as the 30 days the model asked for. Pure functions: no I/O,
# no clock — a window is anchored on the dates the owner block declares (``until`` /
# ``range.end``), not on today's date.

# ``tool_governance.sanitize_tool_result`` replaces a result above 8000 bytes with
# "[omitted:result_too_large]". A list is cut below that here, newest first, and the answer
# states how many items were returned against how many matched.
LIST_BUDGET_BYTES = 6000


def _unavailable(base: dict[str, Any], reason: str, note_ar: str, **extra: Any) -> dict[str, Any]:
    return {**base, "available": False, "reason": reason, "note_ar": note_ar, **extra}


def _valid_days(days: Any) -> bool:
    return isinstance(days, int) and not isinstance(days, bool) and days >= 1


def _iso_day(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _item_day(item: Any, keys: tuple[str, ...]) -> str:
    """ISO day of a list item, or "" when it carries none (sorts last, never in a window)."""
    if isinstance(item, str):
        return item[:10] if _iso_day(item) else ""
    if isinstance(item, dict):
        for key in keys:
            if _iso_day(item.get(key)):
                return str(item[key])[:10]
    return ""


def _fit_budget(items: list[Any]) -> list[Any]:
    kept: list[Any] = []
    size = 2
    for item in items:
        size += len(json.dumps(item, ensure_ascii=False, default=str).encode("utf-8")) + 2
        if size > LIST_BUDGET_BYTES:
            break
        kept.append(item)
    return kept


_SCENE_DATE_KEYS = ("date", "acquisition_date", "acquisition_datetime")


def _indicator_block(pack: dict[str, Any], index: Any) -> tuple[dict[str, Any] | None, str]:
    """(block, "") for a readable index, else (None, reason)."""
    imagery = pack.get("imagery_timeline")
    if not isinstance(imagery, dict) or not isinstance(imagery.get("per_indicator"), dict):
        return None, "imagery_timeline_not_loaded"
    block = imagery["per_indicator"].get(index) if isinstance(index, str) else None
    if not isinstance(block, dict):
        return None, "index_not_in_owner_product"
    return block, ""


_INDEX_NOTES_AR = {
    "imagery_timeline_not_loaded": "حزمة السياق لا تحمل خطّ زمن الصور لهذا الحقل.",
    "index_not_in_owner_product": "المؤشّر المطلوب غير موجود في خطّ زمن الصور المحمَّل.",
    "owner_read_unavailable_for_index": "تعذّرت قراءة هذا المؤشّر من خدمة الراستر عند تحميل الحزمة.",
    "invalid_days": "عدد الأيّام يجب أن يكون عدداً صحيحاً موجباً.",
    "loaded_window_unknown": "الحزمة لا تُعلن النافذة الزمنيّة المحمَّلة، فلا يمكن إثبات النافذة المطلوبة.",
    "requested_window_wider_than_loaded_window": "النافذة المطلوبة أوسع من النافذة المحمَّلة في الحزمة.",
}


def index_timeline(pack: dict[str, Any], field_id: Any, index: Any, days: Any) -> dict[str, Any]:
    """The acquisition dates of ``index`` inside the last ``days`` days of the loaded window."""
    base = {"field_id": field_id, "index": index, "days": days}
    block, reason = _indicator_block(pack, index)
    if block is None:
        return _unavailable(base, reason, _INDEX_NOTES_AR[reason])
    if not _valid_days(days):
        return _unavailable(base, "invalid_days", _INDEX_NOTES_AR["invalid_days"])
    imagery = pack["imagery_timeline"]
    until = _iso_day(imagery.get("until"))
    loaded_days = imagery.get("range_days")
    if until is None or not _valid_days(loaded_days):
        return _unavailable(base, "loaded_window_unknown", _INDEX_NOTES_AR["loaded_window_unknown"])
    loaded = {"since": imagery.get("since"), "until": until.isoformat(), "days": loaded_days}
    if days > loaded_days:
        reason = "requested_window_wider_than_loaded_window"
        return _unavailable(base, reason, _INDEX_NOTES_AR[reason], loaded_window=loaded)
    if block.get("available") is False:
        reason = "owner_read_unavailable_for_index"
        return _unavailable(base, reason, _INDEX_NOTES_AR[reason], loaded_window=loaded)
    since = (until - timedelta(days=days)).isoformat()
    in_window = sorted(
        (
            item
            for item in block.get("dates") or []
            if since <= _item_day(item, _SCENE_DATE_KEYS) <= until.isoformat()
        ),
        key=lambda item: _item_day(item, _SCENE_DATE_KEYS),
        reverse=True,
    )
    kept = _fit_budget(in_window)
    return {
        **base,
        "available": True,
        "window": {"since": since, "until": until.isoformat()},
        "index_timeline": {
            "dates": kept,
            "returned": len(kept),
            "total_in_window": len(in_window),
            "truncated": len(kept) < len(in_window),
        },
    }


def truecolor_scene(
    pack: dict[str, Any], field_id: Any, requested_date: Any, readiness: Any
) -> dict[str, Any]:
    """One TrueColor scene: the requested date, or the newest one when no date is asked."""
    base = {
        "field_id": field_id,
        "index": "truecolor",
        "requested_date": requested_date,
        "readiness": readiness,
    }
    block, reason = _indicator_block(pack, "truecolor")
    if block is None:
        return _unavailable(base, reason, _INDEX_NOTES_AR[reason])
    if block.get("available") is False:
        reason = "owner_read_unavailable_for_index"
        return _unavailable(base, reason, _INDEX_NOTES_AR[reason])
    scenes = [item for item in block.get("dates") or [] if _item_day(item, _SCENE_DATE_KEYS)]
    if requested_date is None:
        if not scenes:
            return _unavailable(
                base, "no_truecolor_scene_loaded", "لا مشهد TrueColor في النافذة المحمَّلة."
            )
        return {
            **base,
            "available": True,
            "scene": max(scenes, key=lambda item: _item_day(item, _SCENE_DATE_KEYS)),
        }
    wanted = _iso_day(requested_date)
    if wanted is None:
        return _unavailable(base, "invalid_date", "التاريخ يجب أن يكون بصيغة ISO (YYYY-MM-DD).")
    for item in scenes:
        if _item_day(item, _SCENE_DATE_KEYS) == wanted.isoformat():
            return {**base, "available": True, "scene": item}
    return _unavailable(
        base,
        "no_truecolor_scene_on_requested_date",
        "لا مشهد TrueColor بالتاريخ المطلوب في النافذة المحمَّلة.",
    )


_WEATHER_NOTES_AR = {
    "weather_history_not_loaded": "حزمة السياق لا تحمل الطقس التاريخيّ لهذا الحقل.",
    "weather_history_unavailable_from_owner": "خدمة الطقس لم تُرجِع طقساً تاريخيّاً عند تحميل الحزمة.",
    "invalid_days": "عدد الأيّام يجب أن يكون عدداً صحيحاً موجباً.",
    "loaded_window_unknown": "الحزمة لا تُعلن نافذة الطقس المحمَّلة، فلا يمكن إثبات النافذة المطلوبة.",
    "requested_window_not_loaded": (
        "الحزمة تحمل ملخّص الطقس وأشهره للنافذة المحمَّلة فقط، بلا سجلّات يوميّة؛ "
        "فلا تُشتقّ منها نافذة أخرى. اطلب النافذة المحمَّلة نفسها."
    ),
}


def weather_history(pack: dict[str, Any], field_id: Any, days: Any) -> dict[str, Any]:
    """The loaded weather block when ``days`` is its own window, else an explicit refusal.

    The pack carries a summary and monthly totals for one window and no daily records, so
    no other window can be cut out of it.
    """
    base = {"field_id": field_id, "days": days}
    block = pack.get("weather_history")
    if not isinstance(block, dict) or not block:
        reason = "weather_history_not_loaded"
        return _unavailable(base, reason, _WEATHER_NOTES_AR[reason])
    if not _valid_days(days):
        return _unavailable(base, "invalid_days", _WEATHER_NOTES_AR["invalid_days"])
    if block.get("available") is not True:
        reason = "weather_history_unavailable_from_owner"
        return _unavailable(base, reason, _WEATHER_NOTES_AR[reason])
    window = block.get("range") if isinstance(block.get("range"), dict) else {}
    start, end = _iso_day(window.get("start")), _iso_day(window.get("end"))
    if start is None or end is None or end < start:
        reason = "loaded_window_unknown"
        return _unavailable(base, reason, _WEATHER_NOTES_AR[reason])
    loaded = {"start": start.isoformat(), "end": end.isoformat(), "days": (end - start).days}
    if days != loaded["days"]:
        reason = "requested_window_not_loaded"
        return _unavailable(base, reason, _WEATHER_NOTES_AR[reason], loaded_window=loaded)
    return {
        **base,
        "available": True,
        "window": {"start": loaded["start"], "end": loaded["end"]},
        "weather_history": block,
    }


def operation_windows(pack: dict[str, Any], field_id: Any) -> dict[str, Any]:
    """The owner's operation-window block, or the statement that the pack carries none."""
    block = pack.get("operation_windows") or pack.get("operation_windows_context")
    if not isinstance(block, dict) or not block:
        return _unavailable(
            {"field_id": field_id},
            "operation_windows_not_in_context_pack",
            "حزمة السياق لا تحمل نوافذ العمليّات؛ لم تُقرأ من خدمة الطقس في هذا الطلب.",
        )
    return {"field_id": field_id, "available": True, "operation_windows": block}
