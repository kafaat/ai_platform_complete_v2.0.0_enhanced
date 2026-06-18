"""core/work_order.py — أمر عمل زراعيّ (Work Order) كآلة حالات نقيّة — أساس FOES.

نظام تنفيذ عمليّات المزرعة (Farm Operations Execution System) هو «MES زراعيّ»: يحوّل
التوصيات (recommendations) إلى **أوامر عمل** قابلة للتنفيذ والتتبّع: ريّ، تسميد، رشّ،
استكشاف (scouting)، حصاد. هذه الوحدة هي **القلب**: آلة حالات صريحة وحتميّة تحكم دورة
حياة أمر العمل من التخطيط حتى التحقّق أو الإلغاء.

نقيّ تماماً: لا I/O ولا قاعدة بيانات ولا حالة عالميّة — منطق انتقالات صرف يُبنى عليه
الراوتر والمهاجرة (migration) لاحقاً. كلّ انتقال غير مسموح يرفع `ValueError` برسالة
عربيّة واضحة، فلا تنزلق الحالة إلى وضع غير صالح.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── الحالات المسموحة لأمر العمل (دورة الحياة) ──
STATUSES: frozenset[str] = frozenset(
    {"planned", "assigned", "in_progress", "done", "verified", "cancelled"}
)

# ── أنواع أوامر العمل الزراعيّة المشتقّة من التوصيات ──
WO_TYPES: frozenset[str] = frozenset(
    {"irrigation", "fertilization", "spraying", "scouting", "harvest"}
)

# ── رسم الانتقالات المسموحة: حالة ⇒ مجموعة الحالات التالية الجائزة ──
# planned→{assigned,cancelled}; assigned→{in_progress,cancelled};
# in_progress→{done,cancelled}; done→{verified, in_progress (إعادة عمل)};
# verified→{} (نهائيّة); cancelled→{} (نهائيّة).
_TRANSITIONS: dict[str, frozenset[str]] = {
    "planned": frozenset({"assigned", "cancelled"}),
    "assigned": frozenset({"in_progress", "cancelled"}),
    "in_progress": frozenset({"done", "cancelled"}),
    "done": frozenset({"verified", "in_progress"}),  # in_progress = إعادة عمل (rework)
    "verified": frozenset(),  # نهائيّة — لا انتقال
    "cancelled": frozenset(),  # نهائيّة — لا انتقال
}


def next_states(status: str) -> set[str]:
    """يُعيد مجموعة الحالات التالية الجائزة من `status` (فارغة إن كانت نهائيّة/مجهولة)."""
    return set(_TRANSITIONS.get(status, frozenset()))


def is_terminal(status: str) -> bool:
    """هل `status` حالة نهائيّة (verified/cancelled) لا انتقال بعدها؟"""
    return status in _TRANSITIONS and not _TRANSITIONS[status]


def can_transition(from_status: str, to_status: str) -> bool:
    """هل الانتقال `from_status → to_status` مسموح في آلة الحالات؟ (نقيّ، بلا أثر)."""
    return to_status in _TRANSITIONS.get(from_status, frozenset())


def transition(current_status: str, to_status: str) -> str:
    """يُنفّذ الانتقال ويُعيد الحالة الجديدة، أو يرفع `ValueError` (عربيّ) إن مُنِع.

    `current_status` الحالة الراهنة لأمر العمل، `to_status` الحالة المطلوبة. لا يغيّر
    شيئاً سوى إرجاع الحالة الجديدة — الاستمرار (persistence) مسؤوليّة الطبقة الأعلى.
    """
    if current_status not in STATUSES:
        raise ValueError(f"حالة غير معروفة: {current_status!r}")
    if to_status not in STATUSES:
        raise ValueError(f"حالة هدف غير معروفة: {to_status!r}")
    if not can_transition(current_status, to_status):
        allowed = sorted(_TRANSITIONS.get(current_status, frozenset()))
        allowed_ar = "، ".join(allowed) if allowed else "(لا شيء — حالة نهائيّة)"
        raise ValueError(
            f"انتقال غير مسموح: {current_status} → {to_status}. "
            f"المسموح من {current_status}: {allowed_ar}."
        )
    return to_status


@dataclass(frozen=True)
class WorkOrder:
    """أمر عمل زراعيّ غير قابل للتغيير (frozen) — لقطة حالة في آلة الحالات.

    يُشتقّ من توصية (`recommendation_id`) ويُنفَّذ على حقل (`field_id`) ضمن مستأجِر
    (`tenant_id`). `wo_type` نوع العمليّة، `status` موضعها في دورة الحياة، `assigned_to`
    المنفّذ، `payload` تفاصيل العمليّة (كمّيّات/توقيت/مدخلات).
    """

    id: str
    field_id: str
    tenant_id: str
    wo_type: str
    status: str = "planned"
    recommendation_id: str | None = None
    assigned_to: str | None = None
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.wo_type not in WO_TYPES:
            raise ValueError(f"نوع أمر عمل غير معروف: {self.wo_type!r}")
        if self.status not in STATUSES:
            raise ValueError(f"حالة غير معروفة: {self.status!r}")

    def with_status(self, to_status: str) -> WorkOrder:
        """يُعيد نسخة جديدة بالحالة المنتقَل إليها (يرفع `ValueError` إن مُنِع الانتقال)."""
        new_status = transition(self.status, to_status)
        return WorkOrder(
            id=self.id,
            field_id=self.field_id,
            tenant_id=self.tenant_id,
            wo_type=self.wo_type,
            status=new_status,
            recommendation_id=self.recommendation_id,
            assigned_to=self.assigned_to,
            payload=self.payload,
        )
