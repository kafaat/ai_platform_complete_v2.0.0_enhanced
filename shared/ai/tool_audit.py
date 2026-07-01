"""عقد تدقيق استدعاءات أدوات الوكيل (V55 — Agricultural Agent Harness).

كلّ استدعاء أداة (tool call) يجب أن يُدوَّن: أيّ أداة، بأيّ وسائط (مُنقَّحة)، بأيّ قدرة
وخطورة، من أيّ مستأجِر/فاعل، ما نتيجته، ومن وافق (للعالية). هذا الملفّ يعرّف **شكل**
السجلّ وتطبيعه وتنقيح وسائطه — عقد صرف. كتابته في القاعدة (جدول تدقيق) تأتي في مرحلة
تالية؛ هنا نضمن الشكل والتنقيح الحتميّين ليصمدا عبر الطبقات.
"""

from __future__ import annotations

import re
from typing import Any

from shared.ai.tool_registry import get_tool

# نتائج استدعاء الأداة القانونيّة.
OUTCOME_EXECUTED = "executed"
OUTCOME_PENDING_APPROVAL = "pending_approval"
OUTCOME_DENIED = "denied"  # قدرة مفقودة أو سياسة تمنع
OUTCOME_FAILED = "failed"
OUTCOMES: tuple[str, ...] = (
    OUTCOME_EXECUTED,
    OUTCOME_PENDING_APPROVAL,
    OUTCOME_DENIED,
    OUTCOME_FAILED,
)

# مفاتيح وسائط لا تُدوَّن أبداً بقيمتها (تُخفى) — أسرار/رموز.
_SECRET_PARAM_HINTS = ("token", "secret", "api_key", "apikey", "password", "authorization")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


def redact_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """يُنقّح وسائط الأداة قبل التدقيق: يُخفي القيم السرّيّة بالاسم، ويُقنّع البريد/
    المعرّفات الكونيّة في القيم النصّيّة. لا يُسرّب أسراراً إلى سجلّ التدقيق."""
    out: dict[str, Any] = {}
    for key, value in (params or {}).items():
        low = str(key).strip().lower()
        if any(h in low for h in _SECRET_PARAM_HINTS):
            out[key] = "[redacted]"
            continue
        if isinstance(value, str):
            masked = _EMAIL_RE.sub("[redacted-email]", value)
            masked = _UUID_RE.sub("[redacted-id]", masked)
            out[key] = masked
        else:
            out[key] = value
    return out


def build_audit_record(
    *,
    tool_name: str,
    params: dict[str, Any] | None,
    tenant_id: str,
    actor: str,
    outcome: str,
    approved_by: str | None = None,
    timestamp: str,
) -> dict[str, Any]:
    """يبني سجلّ تدقيق قانونيّاً لاستدعاء أداة (يُمرَّر ``timestamp`` من الخارج —
    لا وقت داخليّ كي يبقى حتميّاً وقابلاً لإعادة التشغيل).

    يشتقّ ``risk``/``capability``/``requires_approval`` من السجلّ الرسميّ (لا يثق بمُدخَل
    المستدعي فيها). أداة مجهولة ⇒ خطورة عالية وموافقة مطلوبة (fail-closed)."""
    if outcome not in OUTCOMES:
        outcome = OUTCOME_FAILED
    tool = get_tool(tool_name)
    return {
        "tool": tool_name,
        "known_tool": tool is not None,
        "risk": tool.risk if tool else "high",
        "capability": tool.capability if tool else None,
        "requires_approval": tool.requires_approval if tool else True,
        "mutating": tool.mutating if tool else True,
        "params": redact_params(params),
        "tenant_id": str(tenant_id),
        "actor": str(actor),
        "outcome": outcome,
        "approved_by": approved_by,
        "timestamp": timestamp,
    }
