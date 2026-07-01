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

from .approval import build_approval_request, emit_audit
from .tool_executor import (
    OUTCOME_PENDING_APPROVAL,
    execute_read_tool,
    plan_tool_call,
)

logger = logging.getLogger("ai_agronomist.tool_loop")

ToolFetcher = Callable[[str, "dict[str, Any]"], Any]
AuditSaver = Callable[["dict[str, Any]"], None]

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
        params = call.get("params") if isinstance(call.get("params"), dict) else {}

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
        results.append(result)

    return {"tool_calls": results, "pending_approvals": pending, "truncated": truncated}


def _audit_from_result(
    result: dict[str, Any], tenant_id: str, actor: str, timestamp: str
) -> dict[str, Any]:
    """سجلّ تدقيق للنتائج التي لا تحمل واحداً (المؤجَّلة للموافقة)."""
    return {
        "tool": result.get("tool"),
        "params": {},
        "tenant_id": str(tenant_id),
        "actor": str(actor),
        "outcome": result.get("outcome"),
        "risk": result.get("risk"),
        "capability": result.get("capability"),
        "timestamp": timestamp,
        "field_id": None,
        "input_hash": result.get("input_hash"),
        "result_summary": result.get("result_summary") or result.get("reason"),
    }
