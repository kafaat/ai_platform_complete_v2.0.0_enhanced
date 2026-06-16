"""core/tenant_audit.py — سجلّ تدقيق رفض العبور بين المستأجِرين والصلاحيّات.

سجلّ أمنيّ نقيّ في-الذاكرة (deque محدود) يرصد حالات الرفض: محاولة وصول لمورد خارج
نطاق المستأجِر (RLS ⇒ 404)، أو صلاحية غير كافية (403)، أو فشل مصادقة (401). يجعل
محاولات التسرّب العابر للمستأجِرين والرفض مرئيّةً للمراقبة بدل ضياعها في السجلّات.

نمط مطابق لـcore.automation_ledger (singleton + deque + recent/summary). لا قاعدة،
لا هجرات. صدق وخصوصيّة: يُخزَّن فقط ما يُمرَّر — مُعرّفات (user_id/tenant_id الموجودة
في الـJWT) لا أسرار/توكنات. لا يرفع استثناءً (التدقيق لا يكسر المسار).
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

_KINDS = ("tenant_scope", "permission", "auth")


@dataclass
class DenialRecord:
    """سجلّ رفض واحد — مُعرّفات فقط (لا توكنات/أسرار)."""

    at: str  # ISO timestamp (UTC)
    kind: str  # tenant_scope | permission | auth
    user_id: str | None = None
    tenant_id: str | None = None
    resource: str | None = None
    action: str | None = None
    reason_ar: str | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class TenantAuditLog:
    """سجلّ تدقيق محدود (ring buffer) لحالات الرفض الأمنيّ — في-الذاكرة، آمن للحلقة."""

    def __init__(self, maxlen: int = 200) -> None:
        self._buf: deque[DenialRecord] = deque(maxlen=maxlen)
        self.maxlen = maxlen

    def record(
        self,
        kind: str,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        resource: str | None = None,
        action: str | None = None,
        reason_ar: str | None = None,
        detail: dict | None = None,
    ) -> DenialRecord:
        """يسجّل حالة رفض — لا يرفع استثناءً أبداً (التدقيق لا يكسر المسار)."""
        rec = DenialRecord(
            at=datetime.now(UTC).isoformat(),
            kind=kind if kind in _KINDS else "permission",
            user_id=user_id,
            tenant_id=tenant_id,
            resource=resource,
            action=action,
            reason_ar=reason_ar,
            detail=detail or {},
        )
        self._buf.append(rec)
        return rec

    def recent(self, limit: int | None = None) -> list[dict]:
        """أحدث حالات الرفض أوّلاً (الأجدد ⇐ الأقدم)."""
        items = list(reversed(self._buf))
        if limit is not None:
            items = items[: max(0, int(limit))]
        return [r.to_dict() for r in items]

    def summary(self) -> dict:
        """ملخّص: الإجماليّ + العدد لكلّ نوع + وقت آخر رفض."""
        by_kind: dict[str, int] = {}
        for r in self._buf:
            by_kind[r.kind] = by_kind.get(r.kind, 0) + 1
        last_at = self._buf[-1].at if self._buf else None
        return {
            "total": len(self._buf),
            "buffer_capacity": self.maxlen,
            "by_kind": by_kind,
            "last_at": last_at,
        }

    def clear(self) -> None:
        """يُفرّغ السجلّ (للاختبار/إعادة الضبط)."""
        self._buf.clear()


# singleton مشترك بين مواضع الرفض ونقطة القراءة.
AUDIT = TenantAuditLog()
