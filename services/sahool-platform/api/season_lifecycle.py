"""api/season_lifecycle.py — دورة حياة الموسم (انتقالات الحالة) — نواة نقيّة.

يدعم نقطة تحديث الموسم الصريحة (PATCH) بمصدر واحد لقواعد انتقال الحالة، قابل
للاختبار offline (لا I/O). يُكمّل تغطية أحداث الموسم (SEASON_UPDATED) بعد
SEASON_CREATED/SEASON_CLOSED.

⚠ المبدأ:
  • انتقالات صريحة حتميّة: planned→active/closed، active→closed، closed نهائيّ.
  • لا «إحياء» موسم مُغلَق (يحفظ التاريخ وثابت «موسم نشط واحد»).
  • نفس الحالة = لا-عمل مسموح (idempotent)، لا انتقال.
  • حالة مجهولة → خطأ صريح (422)، لا تخمين.
"""

from __future__ import annotations

from enum import Enum


class SeasonStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    CLOSED = "closed"


# مصدر واحد لقواعد الانتقال (الحالة → الحالات المسموح الانتقال إليها).
SEASON_TRANSITIONS: dict[SeasonStatus, set[SeasonStatus]] = {
    SeasonStatus.PLANNED: {SeasonStatus.ACTIVE, SeasonStatus.CLOSED},
    SeasonStatus.ACTIVE: {SeasonStatus.CLOSED},
    SeasonStatus.CLOSED: set(),  # نهائيّ — لا إحياء
}


class SeasonTransitionError(Exception):
    """انتقال حالة موسم غير مسموح/مجهول — يحمل رسالة عربيّة ورمز HTTP (422)."""

    def __init__(self, message_ar: str, http_status: int = 422):
        super().__init__(message_ar)
        self.message_ar = message_ar
        self.http_status = http_status


def _coerce(status: str | SeasonStatus) -> SeasonStatus:
    try:
        return SeasonStatus(status)
    except ValueError as e:
        allowed = "، ".join(s.value for s in SeasonStatus)
        raise SeasonTransitionError(f"حالة موسم مجهولة '{status}' (المسموح: {allowed})") from e


def validate_status_transition(current: str | SeasonStatus, target: str | SeasonStatus) -> bool:
    """يتحقّق من شرعيّة انتقال حالة الموسم — حتميّ شفّاف.

    يُرجِع True إن كان انتقالاً فعليّاً مسموحاً، False إن كانت الحالة نفسها (لا-عمل).
    يرفع SeasonTransitionError (422) لانتقال غير مسموح أو حالة مجهولة.
    """
    cur, tgt = _coerce(current), _coerce(target)
    if cur == tgt:
        return False  # لا-عمل (idempotent) — لا تغيير حالة
    if tgt in SEASON_TRANSITIONS[cur]:
        return True
    allowed = SEASON_TRANSITIONS[cur]
    allowed_ar = "، ".join(s.value for s in allowed) if allowed else "لا شيء (حالة نهائيّة)"
    raise SeasonTransitionError(
        f"انتقال غير مسموح: {cur.value} → {tgt.value} (المسموح من {cur.value}: {allowed_ar})"
    )
