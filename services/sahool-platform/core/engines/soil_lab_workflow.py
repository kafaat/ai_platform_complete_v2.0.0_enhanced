"""core/engines/soil_lab_workflow.py — دورة حياة فحص التربة المخبري (نواة نقيّة).

ينفّذ بند «Workflow مخبري للتربة» من خارطة ما بعد التشغيل: عيّنة → مختبر → نتيجة →
اعتماد → نشر. يستبدل أعمدة soil_* الثابتة بدورة حياة موثَّقة، بمصدر واحد لقواعد
الانتقال + invariant «لا اعتماد/نشر بلا نتيجة مختبر». نواة نقيّة (لا I/O) قابلة
للاختبار offline.

⚠ المبدأ:
  • انتقالات صريحة حتميّة (مصدر واحد) — لا قفز فوق المراحل.
  • صدق: لا اعتماد ولا نشر بلا نتيجة مختبر فعليّة (invariant — لا تأليف قيم تربة).
  • مرفوض → إعادة فحص أو إلغاء (لا «إحياء» منشور/ملغى — نهائيّان).
  • نفس الحالة = لا-عمل (idempotent). حالة مجهولة → 422 صريح.
"""

from __future__ import annotations

from enum import Enum


class SoilTestStatus(str, Enum):
    REQUESTED = "requested"  # طُلبت عيّنة
    SAMPLED = "sampled"  # جُمعت العيّنة ميدانيّاً
    IN_LAB = "in_lab"  # أُرسلت للمختبر
    RESULT_RECEIVED = "result_received"  # وردت نتيجة المختبر
    APPROVED = "approved"  # اعتمدها المهندس الزراعي
    PUBLISHED = "published"  # نُشرت (بيانات التربة المرجعيّة للحقل)
    REJECTED = "rejected"  # رُفضت النتيجة (إعادة فحص أو إلغاء)
    CANCELLED = "cancelled"  # أُلغي الفحص (نهائيّ)


# مصدر واحد لقواعد الانتقال (الحالة → الحالات المسموح الانتقال إليها).
SOIL_TEST_TRANSITIONS: dict[SoilTestStatus, set[SoilTestStatus]] = {
    SoilTestStatus.REQUESTED: {SoilTestStatus.SAMPLED, SoilTestStatus.CANCELLED},
    SoilTestStatus.SAMPLED: {SoilTestStatus.IN_LAB, SoilTestStatus.CANCELLED},
    SoilTestStatus.IN_LAB: {SoilTestStatus.RESULT_RECEIVED, SoilTestStatus.CANCELLED},
    SoilTestStatus.RESULT_RECEIVED: {SoilTestStatus.APPROVED, SoilTestStatus.REJECTED},
    SoilTestStatus.APPROVED: {SoilTestStatus.PUBLISHED},
    SoilTestStatus.REJECTED: {SoilTestStatus.IN_LAB, SoilTestStatus.CANCELLED},
    SoilTestStatus.PUBLISHED: set(),  # نهائيّ
    SoilTestStatus.CANCELLED: set(),  # نهائيّ
}

# حالات تتطلّب نتيجة مختبر فعليّة (صدق: لا اعتماد/نشر بلا قياس).
_REQUIRES_RESULT = {
    SoilTestStatus.RESULT_RECEIVED,
    SoilTestStatus.APPROVED,
    SoilTestStatus.PUBLISHED,
}


class SoilWorkflowError(Exception):
    """انتقال حالة فحص تربة غير مسموح/مجهول أو invariant مكسور — رسالة + رمز HTTP."""

    def __init__(self, message_ar: str, http_status: int = 422):
        super().__init__(message_ar)
        self.message_ar = message_ar
        self.http_status = http_status


def _coerce(status: str | SoilTestStatus) -> SoilTestStatus:
    try:
        return SoilTestStatus(status)
    except ValueError as e:
        allowed = "، ".join(s.value for s in SoilTestStatus)
        raise SoilWorkflowError(f"حالة فحص مجهولة '{status}' (المسموح: {allowed})") from e


def validate_soil_transition(
    current: str | SoilTestStatus,
    target: str | SoilTestStatus,
    *,
    has_result: bool = False,
) -> bool:
    """يتحقّق من شرعيّة انتقال حالة فحص التربة + invariant النتيجة — حتميّ شفّاف.

    يُرجِع True لانتقال فعليّ مسموح، False لنفس الحالة (لا-عمل). يرفع SoilWorkflowError
    (422) لانتقال غير مسموح/حالة مجهولة، أو لانتقال يتطلّب نتيجة مختبر وهي غائبة.
    """
    cur, tgt = _coerce(current), _coerce(target)
    if cur == tgt:
        return False  # لا-عمل (idempotent)
    if tgt not in SOIL_TEST_TRANSITIONS[cur]:
        allowed = SOIL_TEST_TRANSITIONS[cur]
        allowed_ar = "، ".join(s.value for s in allowed) if allowed else "لا شيء (نهائيّة)"
        raise SoilWorkflowError(
            f"انتقال غير مسموح: {cur.value} → {tgt.value} (المسموح: {allowed_ar})"
        )
    if tgt in _REQUIRES_RESULT and not has_result:
        raise SoilWorkflowError(
            f"لا يمكن الانتقال إلى {tgt.value} بلا نتيجة مختبر — أدخِل النتيجة أوّلاً (صدق)."
        )
    return True
