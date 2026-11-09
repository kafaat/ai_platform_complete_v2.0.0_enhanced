"""core/engines/harvest_traceability.py — منطق تتبّع سلسلة الإمداد (نقيّ، بلا DB).

يكمّل input_traceability (تتبّع المدخلات على مستوى الحقل) بسلسلة الحيازة من الحصاد
إلى السوق. كلّ الدوالّ هنا نقيّة (لا I/O) فتُختبَر offline، والراوتر يلفّها بالقاعدة.

- compute_event_hash: SHA-256 حتميّ لمحتوى حدث الحيازة (سلامة السجلّ append-only).
- status_for_event: الحالة الجديدة للدفعة المُشتقّة من نوع حدث الحيازة (وفحص راسب ⇒ rejected).
- transition_refusal: سبب رفض حدث غير مسموح (بيع المرفوض، الرجوع عن البيع) — 409 في الراوتر.
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


# اصطلاح نتيجة فحص الجودة في event_details (لا عمود مخصّص في v65): أيّ من
#   passed: false · result ∈ {fail, failed, reject, rejected} · grade/quality_grade = reject
# يعني فحصاً راسباً ⇒ الدفعة «rejected». غياب هذه المفاتيح ⇒ فحص لا يحرّك الحالة.
_FAILED_RESULTS = frozenset({"fail", "failed", "reject", "rejected"})
# حالات «ما قبل البيع» التي لا تعود إليها دفعة مُباعة (البيع لا يُنقَض بحدث حركة).
_PRE_SALE_STATUSES = frozenset({"harvested", "stored", "in_transit", "at_market"})


def quality_check_failed(event_details: dict[str, Any] | None) -> bool:
    """هل تفاصيل فحص الجودة تقول «راسب»؟ اصطلاح صريح ضيّق — لا استدلال من نصّ حرّ."""
    details = event_details or {}
    if details.get("passed") is False:
        return True
    result = details.get("result")
    if isinstance(result, str) and result.strip().lower() in _FAILED_RESULTS:
        return True
    for key in ("grade", "quality_grade"):
        grade = details.get(key)
        if isinstance(grade, str) and grade.strip().lower() == "reject":
            return True
    return False


def status_for_event(
    event_type: str, current_status: str, event_details: dict[str, Any] | None = None
) -> str:
    """الحالة الجديدة للدفعة بعد حدث حيازة. النوع المجهول أو غير المُحرِّك ⇒ تبقى الحالة.

    فحص جودة راسب ⇒ «rejected» (إلّا على دفعة مُباعة: البيع لا يُعاد كتابته، والفحص
    يبقى دليلاً في السلسلة). فحص ناجح لا يُلغي رفضاً سابقاً.
    """
    if event_type == "quality_check":
        if quality_check_failed(event_details) and current_status != "sold":
            return "rejected"
        return current_status
    nxt = _EVENT_TO_STATUS.get(event_type)
    return nxt if nxt is not None else current_status


def transition_refusal(
    event_type: str,
    current_status: str,
    *,
    quality_grade: str | None = None,
    event_details: dict[str, Any] | None = None,
) -> str | None:
    """سبب رفض الحدث (نصّ عربيّ) أو None إن كان مسموحاً — يُترجمه الراوتر إلى 409.

    - بيع دفعة مرفوضة (حالة rejected) أو مُصنَّفة reject عند الإنشاء ⇒ مرفوض.
    - إعادة دفعة مُباعة إلى حالة ما قبل البيع (حصاد/تخزين/نقل) ⇒ مرفوض.
    """
    if event_type == "sales":
        if current_status == "rejected":
            return "لا يمكن بيع دفعة مرفوضة في فحص الجودة"
        if isinstance(quality_grade, str) and quality_grade.strip().lower() == "reject":
            return "لا يمكن بيع دفعة مُصنَّفة reject"
    if current_status == "sold":
        nxt = status_for_event(event_type, current_status, event_details)
        if nxt in _PRE_SALE_STATUSES:
            return "الدفعة مُباعة — لا تعود إلى حالة ما قبل البيع"
    return None


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
