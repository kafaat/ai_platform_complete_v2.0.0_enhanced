"""بوّابة الموافقة البشريّة + إدامة تدقيق الأدوات (V55 — المرحلة ٤).

الأفعال عالية الأثر لا تُنفَّذ بقرار النموذج وحده: المنفّذ (المرحلة ٢) يُرجِع
``pending_approval``؛ هنا نُنشئ **طلب موافقة** يُدِيمه إنسان يقبله أو يرفضه، وكلّ ذلك
(وكلّ استدعاء أداة) يُدوَّن في سجلّ ``agent_tool_audit`` الدائم (v126، append-only).

دوالّ صرفة + حاقن إدامة (لا قاعدة في الاختبار). ``timestamp`` يُمرَّر من الخارج
(حتميّ). الوسائط تُنقَّح دائماً قبل الحفظ (لا أسرار في التدقيق).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("ai_agronomist.approval")

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_DENIED = "denied"
STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_DENIED)

_SECRET_HINTS = ("token", "secret", "api_key", "apikey", "password", "authorization")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# حاقن إدامة سجلّ التدقيق (يكتب صفّاً في agent_tool_audit). بلا حاقن ⇒ لا كتابة دائمة.
AuditSaver = Callable[["dict[str, Any]"], None]


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


def build_approval_request(
    *,
    request_id: str,
    tool_name: str,
    params: dict[str, Any] | None,
    tenant_id: str,
    actor: str,
    risk: str,
    capability: str | None,
    requested_at: str,
) -> dict[str, Any]:
    """يُنشئ طلب موافقة معلَّقاً لأداة مؤجَّلة (وسائطه مُنقَّحة)."""
    return {
        "id": str(request_id),
        "tool": tool_name,
        "params": _redact(params),
        "tenant_id": str(tenant_id),
        "actor": str(actor),
        "risk": risk,
        "capability": capability,
        "status": STATUS_PENDING,
        "requested_at": requested_at,
        "decided_by": None,
        "decided_at": None,
        "deny_reason": None,
    }


def approve(request: dict[str, Any], *, approver: str, decided_at: str) -> dict[str, Any]:
    """يوافق على طلب معلَّق (لا يوافق على غير المعلَّق — حماية من الموافقة المزدوجة)."""
    if request.get("status") != STATUS_PENDING:
        raise ValueError(f"لا يمكن الموافقة على طلب حالته {request.get('status')}")
    updated = dict(request)
    updated.update(
        {"status": STATUS_APPROVED, "decided_by": str(approver), "decided_at": decided_at}
    )
    return updated


def deny(
    request: dict[str, Any], *, approver: str, decided_at: str, reason: str = ""
) -> dict[str, Any]:
    if request.get("status") != STATUS_PENDING:
        raise ValueError(f"لا يمكن رفض طلب حالته {request.get('status')}")
    updated = dict(request)
    updated.update(
        {
            "status": STATUS_DENIED,
            "decided_by": str(approver),
            "decided_at": decided_at,
            "deny_reason": reason,
        }
    )
    return updated


def emit_audit(record: dict[str, Any], saver: AuditSaver | None) -> bool:
    """يُدِيم سجلّ تدقيق (best-effort). يُنقّح الوسائط قبل الحفظ. فشل الحفظ لا يرفع
    استثناءً للمستدعي (التدقيق لا يجب أن يُعطّل المسار). يُرجِع نجاح الإدامة."""
    safe = dict(record)
    safe["params"] = _redact(record.get("params") if isinstance(record.get("params"), dict) else {})
    if saver is None:
        return False
    try:
        saver(safe)
        return True
    except Exception as exc:  # التدقيق best-effort — لا يُعطّل استدعاء الأداة.
        logger.warning("فشل إدامة تدقيق الأداة %s: %s", record.get("tool"), exc)
        return False
