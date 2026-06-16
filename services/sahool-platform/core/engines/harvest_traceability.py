"""core/engines/harvest_traceability.py — منطق تتبّع سلسلة الإمداد (نقيّ، بلا DB).

يكمّل input_traceability (تتبّع المدخلات على مستوى الحقل) بسلسلة الحيازة من الحصاد
إلى السوق. كلّ الدوالّ هنا نقيّة (لا I/O) فتُختبَر offline، والراوتر يلفّها بالقاعدة.

- compute_event_hash: SHA-256 حتميّ لمحتوى حدث الحيازة (سلامة السجلّ append-only).
- status_for_event: الحالة الجديدة للدفعة المُشتقّة من نوع حدث الحيازة.
- assemble_traceability: يجمع الدفعة + السلسلة المرتّبة زمنيّاً + المنشأ + تقييم
  اكتمال السلسلة في أثر واحد جاهز للـJSON.
- ثوابت التحقّق (الأنواع/الأدوار) — مصدر حقيقة واحد يشاركه الراوتر والاختبار.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# مجموعات القيم المسموحة — تطابق قيود CHECK في v65_harvest_traceability.sql.
CUSTODY_EVENT_TYPES: tuple[str, ...] = (
    "harvest",
    "storage",
    "quality_check",
    "transport",
    "sales",
)
HANDLER_ROLES: tuple[str, ...] = (
    "farmer",
    "storage",
    "transporter",
    "trader",
    "buyer",
    "inspector",
    "system",
)
LOT_STATUSES: tuple[str, ...] = (
    "harvested",
    "stored",
    "in_transit",
    "at_market",
    "sold",
    "rejected",
)

# انتقال حالة الدفعة المُشتقّ من نوع حدث الحيازة (تطبيقيّ). None ⇒ لا تغيّر الحالة
# (فحص الجودة لا يحرّك موضع الدفعة). يحرّكه الراوتر عند تسجيل حدث.
_EVENT_TO_STATUS: dict[str, str | None] = {
    "harvest": "harvested",
    "storage": "stored",
    "transport": "in_transit",
    "quality_check": None,
    "sales": "sold",
}


def status_for_event(event_type: str, current_status: str) -> str:
    """الحالة الجديدة للدفعة بعد حدث حيازة. النوع المجهول أو غير المُحرِّك ⇒ تبقى الحالة."""
    nxt = _EVENT_TO_STATUS.get(event_type)
    return nxt if nxt is not None else current_status


def compute_event_hash(
    harvest_lot_id: str,
    event_type: str,
    occurred_at: str,
    event_details: dict[str, Any] | None,
) -> str:
    """SHA-256 حتميّ لمحتوى حدث الحيازة — يكشف أيّ تلاعب لاحق بالسجلّ append-only.

    تمثيل قانونيّ (sort_keys + فواصل ثابتة) فيُنتج نفس البصمة لنفس المحتوى بصرف
    النظر عن ترتيب مفاتيح الإدخال. نقيّ وحتميّ (قابل لإعادة الحساب والتحقّق)."""
    canonical = json.dumps(
        {
            "lot": harvest_lot_id,
            "type": event_type,
            "at": occurred_at,
            "details": event_details or {},
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assemble_traceability(
    lot: dict[str, Any],
    custody_events: list[dict[str, Any]],
    origin: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """يبني الأثر الكامل لدفعة: الدفعة + سلسلة الحيازة مرتّبة زمنيّاً + المنشأ + تقييم
    الاكتمال (بدأت بحصاد؟ بلغت السوق؟). نقيّ: يقبل dicts مُطبّعة ويُرجِع dict للـJSON.

    ترتيب السلسلة بـ(occurred_at, custody_event_id) حتميّ — يطابق فهرس الاستعلام،
    وكاسر التعادل (id تسلسليّ) يمنع اختلاف الترتيب عند تساوي occurred_at."""
    chain = sorted(
        custody_events,
        key=lambda e: (e.get("occurred_at") or "", e.get("custody_event_id") or 0),
    )
    has_harvest = any(e.get("event_type") == "harvest" for e in chain)
    reached_market = any(e.get("event_type") == "sales" for e in chain)
    return {
        "harvest_lot": lot,
        "custody_chain": chain,
        "origin": origin or {},
        "chain": {
            "event_count": len(chain),
            "started_at_harvest": has_harvest,
            "reached_market": reached_market,
            # «كامل» = بدأت بحصاد وبلغت بيعاً (أبسط معيار تتبّع من المزرعة للسوق).
            "complete": has_harvest and reached_market,
        },
    }
