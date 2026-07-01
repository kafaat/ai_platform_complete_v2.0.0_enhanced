"""حلقة استدعاء الأدوات المحوكَمة (V56 — الوصل الحيّ).

النموذج يُرجِع طلبات أدوات (tool_calls)؛ هذه الحلقة تُنفّذها **عبر بوّابة الحوكمة**
(المرحلة ٢): أدوات القراءة تُنفَّذ فوراً بجالب محقون؛ المُعدِّلة/العالية تُحوَّل إلى
طلبات موافقة بشريّة (لا تُنفَّذ)؛ كلّ استدعاء يُدوَّن. مُقيَّدة العدد (منع الإفراط).

دالّة صرفة قابلة للاختبار: الجالب (نداءات القراءة الحيّة) وحاقن التدقيق يُمرَّران —
لا خدمات ولا نموذج حيّ هنا. ``timestamp`` من الخارج (حتميّ). تُرجِع نتائج جاهزة
لـ``harness_transparency`` (المرحلة ٥).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from . import tool_governance
from .approval import build_approval_request, emit_audit
from .tool_executor import (
    OUTCOME_PENDING_APPROVAL,
    execute_read_tool,
    plan_tool_call,
)

logger = logging.getLogger("ai_agronomist.tool_loop")

ToolFetcher = Callable[[str, "dict[str, Any]"], Any]
AuditSaver = Callable[["dict[str, Any]"], None]
ApprovalSaver = Callable[["dict[str, Any]"], None]

MAX_TOOL_CALLS = 8  # سقف صارم: يمنع حلقة أدوات لا تنتهي.


def run_tool_calls(
    tool_calls: list[dict[str, Any]] | None,
    *,
    allowed_capabilities: list[str] | None,
    fetcher: ToolFetcher | None,
    tenant_id: str,
    actor: str,
    timestamp: str,
    audit_saver: AuditSaver | None = None,
    approval_saver: ApprovalSaver | None = None,
    max_calls: int = MAX_TOOL_CALLS,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """يُنفّذ طلبات أدوات النموذج عبر الحوكمة. كلّ عنصر: ``{tool, params?, id?}``.

    يُرجِع: ``{tool_calls: [...نتائج...], pending_approvals: [...], truncated: bool}``
    — جاهزةً لإسقاط الشفافيّة. القراءة المسموحة تُنفَّذ؛ المُعدِّلة/العالية ⇒ طلب موافقة."""
    requests = [c for c in (tool_calls or []) if isinstance(c, dict)]
    truncated = len(requests) > max_calls
    requests = requests[:max_calls]

    results: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    for idx, call in enumerate(requests):
        name = str(call.get("tool") or "")
        raw_params = call.get("params")
        params = raw_params if isinstance(raw_params, dict) else {}
        call_id = str(call.get("id") or f"req-{idx}")

        # V58.2b — reject malformed/missing-required/bad-enum args BEFORE any execution
        # or approval request (explicit outcome, fail-closed — never run with silent {}).
        ok, reason = tool_governance.validate_tool_args(
            name, raw_params if raw_params is not None else {}
        )
        if not ok:
            result = tool_governance.malformed_result(name, call_id, reason or "invalid_arguments")
            emit_audit(_audit_from_result(result, tenant_id, actor, timestamp), audit_saver)
            results.append(result)
            continue

        plan = plan_tool_call(name, params, allowed_capabilities)
        if plan["outcome"] == OUTCOME_PENDING_APPROVAL:
            # فعل مُعدِّل/عالٍ: لا يُنفَّذ — يُنشأ طلب موافقة بشريّة (المرحلة ٤).
            req = build_approval_request(
                request_id=str(call.get("id") or f"req-{idx}"),
                tool_name=name,
                params=params,
                tenant_id=tenant_id,
                actor=actor,
                risk=plan["risk"],
                capability=plan["capability"],
                requested_at=timestamp,
            )
            pending.append(req)
            if approval_saver is not None:
                try:
                    approval_saver(req)
                except Exception as exc:  # best-effort: approval persistence must not break chat.
                    logger.warning("فشل حفظ طلب الموافقة %s: %s", req.get("id"), exc)
            result = {
                "tool_call_id": str(call.get("id") or f"req-{idx}"),
                "tool": name,
                "outcome": OUTCOME_PENDING_APPROVAL,
                "reason": plan["reason"],
                "risk": plan["risk"],
                "capability": plan["capability"],
                "requires_approval": plan["requires_approval"],
                "data": None,
                "approval_id": req["id"],
                "params": params,
                "input_hash": req["input_hash"],
                "field_id": params.get("field_id"),
                "result_summary": req["result_summary"],
            }
        else:
            # قراءة مسموحة (أو مرفوضة) — المنفّذ يحكم ويُدوّن؛ لا كتابة هنا.
            result = execute_read_tool(
                name,
                params,
                allowed_capabilities,
                fetcher,
                tenant_id=tenant_id,
                actor=actor,
                timestamp=timestamp,
            )
            result["tool_call_id"] = str(call.get("id") or f"req-{idx}")

        audit_record = result.get("audit") or _audit_from_result(
            result, tenant_id, actor, timestamp
        )
        if provider:
            audit_record["provider"] = provider
        if model:
            audit_record["model"] = model
        audit_record.setdefault("field_id", params.get("field_id"))
        emit_audit(audit_record, audit_saver)
        # V58.2b — sanitize the result before it re-enters the model context (tool-result
        # prompt-injection / poisoning defence). Pending-approval envelopes are NOT sanitized:
        # they carry approval metadata (approval_id/input_hash) the UI needs verbatim and are
        # never fed back to the LLM as tool output.
        if result.get("outcome") == OUTCOME_PENDING_APPROVAL:
            results.append(result)
        else:
            results.append(tool_governance.sanitize_tool_result(result))

    return {"tool_calls": results, "pending_approvals": pending, "truncated": truncated}


def _audit_from_result(
    result: dict[str, Any], tenant_id: str, actor: str, timestamp: str
) -> dict[str, Any]:
    """سجلّ تدقيق للنتائج التي لا تحمل واحداً (خصوصاً طلبات الموافقة)."""
    params = result.get("params") if isinstance(result.get("params"), dict) else {}
    return {
        "tool": result.get("tool"),
        "params": params,
        "tenant_id": str(tenant_id),
        "actor": str(actor),
        "outcome": result.get("outcome"),
        "risk": result.get("risk"),
        "capability": result.get("capability"),
        "timestamp": timestamp,
        "field_id": result.get("field_id") or params.get("field_id"),
        "input_hash": result.get("input_hash"),
        "result_summary": result.get("result_summary") or result.get("reason"),
        "result": {"reason": result.get("reason"), "approval_id": result.get("approval_id")},
    }
