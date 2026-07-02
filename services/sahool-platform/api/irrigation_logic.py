"""api/irrigation_logic.py — منطق الريّ النقيّ (بلا fastapi/pydantic، stdlib فقط).

استُخرِج من ``irrigation_models.py`` (الذي يستورد ``fastapi.HTTPException`` لـ``_parse_time``)
كي تُختبَر هذه الدوالّ الصرفة في طبقة *الوحدة* في CI حيث لا fastapi. ``irrigation_models``
يعيد تصديرها فيبقى ``api.routers.irrigation`` يستوردها كما هو.

- ``plan_run_ledger_action`` (v29.5-op-2): أثر تبدّل حالة الصمّام على دفتر irrigation_runs.
- ``schedules_overlap`` (v29.5-op-3): تداخُل جدولَي ريّ متكرّرَين على دورة أسبوعيّة 7×1440 دقيقة.
"""

from __future__ import annotations

_MIN_PER_DAY = 1440
_MIN_PER_WEEK = 7 * _MIN_PER_DAY


def plan_run_ledger_action(status: str) -> str | None:
    """دالّة صرفة: تقرّر أثر تبدّل حالة الصمّام على دفتر التشغيل.

    - ``"open"``   ⇒ ``"open_run"``  (افتح صفّ تشغيل جديداً، status='running').
    - ``"closed"`` ⇒ ``"close_run"`` (أغلق أحدث تشغيل جارٍ لهذا الصمّام).
    - أيّ قيمة أخرى ⇒ ``None`` (لا أثر — لا نخترع تشغيلاً).
    """
    if status == "open":
        return "open_run"
    if status == "closed":
        return "close_run"
    return None


def _time_to_minutes(value) -> float:
    """time → دقائق منذ منتصف الليل (تشمل الثواني ككسر). يقبل أيضاً رقماً جاهزاً."""
    if isinstance(value, (int, float)):
        return float(value)
    return value.hour * 60 + value.minute + value.second / 60.0


def _normalize_days(days) -> list[int]:
    """None ⇒ يوميّاً (0..6)؛ وإلّا القيم الصالحة 0..6 مُرتّبة بلا تكرار."""
    if days is None:
        return list(range(7))
    return sorted({int(d) for d in days if 0 <= int(d) <= 6})


def _weekly_intervals(start_min: float, duration_min: float, days) -> list[tuple[float, float]]:
    """فترات [بداية، نهاية) على التقويم الأسبوعيّ [0, 10080) لكلّ يوم فعّال، مع تقسيم
    اللفّ عند نهاية الأسبوع (نافذة قد تمتدّ إلى اليوم/الأسبوع التالي)."""
    out: list[tuple[float, float]] = []
    for d in _normalize_days(days):
        lo = (d * _MIN_PER_DAY + start_min) % _MIN_PER_WEEK
        hi = lo + duration_min
        if hi <= _MIN_PER_WEEK:
            out.append((lo, hi))
        else:
            out.append((lo, _MIN_PER_WEEK))
            out.append((0.0, hi - _MIN_PER_WEEK))
    return out


def schedules_overlap(
    a_start,
    a_duration_min: float,
    a_days,
    b_start,
    b_duration_min: float,
    b_days,
) -> bool:
    """هل يتداخل جدولا ريّ (نفس الصمّام) زمنيّاً على الدورة الأسبوعيّة؟

    ``*_start`` إمّا ``datetime.time`` أو دقائق منذ منتصف الليل. النوافذ نصف مفتوحة
    ([lo, hi)) فجدولان متلاصقان (ينتهي أحدهما عند بدء الآخر) لا يُعدّان تعارضاً.
    """
    a = _weekly_intervals(_time_to_minutes(a_start), a_duration_min, a_days)
    b = _weekly_intervals(_time_to_minutes(b_start), b_duration_min, b_days)
    return any(a0 < b1 and b0 < a1 for (a0, a1) in a for (b0, b1) in b)
