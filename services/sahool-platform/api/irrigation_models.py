"""api/irrigation_models.py — نماذج/مساعِدات الريّ التشغيليّ (صمامات + جداول).

شريحة من تفكيك ``api/main.py`` (نمط B1): النماذج (``ValveRequest`` /
``ValveStateRequest`` / ``ScheduleRequest``) والمساعِد ``_parse_time`` نُقِلت
حرفيّاً إلى هنا. self-contained: pydantic فقط للنماذج، و``datetime`` +
``fastapi.HTTPException`` لـ``_parse_time``. يستوردها ``api.routers.irrigation``.
"""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field


class ValveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    field_id: str | None = None
    device_id: str | None = None
    valve_type: str = Field(default="solenoid", pattern="^(solenoid|manual|drip_header|gate)$")
    flow_rate_lpm: float | None = Field(default=None, ge=0)


class ValveStateRequest(BaseModel):
    status: str = Field(pattern="^(open|closed)$")
    # اختياريّان (v29.5-op-2): إن حملتهما الحمولة عند الإغلاق يُدوَّن حجم ماء التشغيل
    # في irrigation_runs، وإلّا NULL (لا تلفيق). إضافيّان متوافقان مع القديم.
    volume_l: float | None = Field(default=None, ge=0)
    volume_mm: float | None = Field(default=None, ge=0)


class ScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    field_id: str | None = None
    valve_id: str | None = None
    start_time: str  # HH:MM أو HH:MM:SS
    duration_min: int = Field(ge=1, le=1440)
    days_of_week: list[int] | None = None
    water_target_mm: float | None = Field(default=None, ge=0)
    enabled: bool = True


def plan_run_ledger_action(status: str) -> str | None:
    """دالّة صرفة (قابلة لاختبار وحدة): تقرّر أثر تبدّل حالة الصمّام على دفتر التشغيل.

    - ``"open"``   ⇒ ``"open_run"``  (افتح صفّ تشغيل جديداً، status='running').
    - ``"closed"`` ⇒ ``"close_run"`` (أغلق أحدث تشغيل جارٍ لهذا الصمّام).
    - أيّ قيمة أخرى ⇒ ``None`` (لا أثر على الدفتر — لا نخترع تشغيلاً).

    self-contained هنا (بلا api.main) كي يُختبَر القرار بلا قاعدة بيانات (v29.5-op-2).
    """
    if status == "open":
        return "open_run"
    if status == "closed":
        return "close_run"
    return None


def _parse_time(value: str):
    """يحوّل HH:MM[:SS] إلى time؛ 400 على قيمة غير صالحة (لا 500)."""
    from datetime import time as _time

    try:
        return _time.fromisoformat(value.strip())
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=400, detail="start_time غير صالح — استخدم HH:MM أو HH:MM:SS"
        ) from None


# ════════════════════════════════════════════════════════════════════════════
# كشف تعارُض جداول الريّ (v29.5-op-3) — منطق نقيّ (بلا قاعدة، قابل للاختبار وحدةً)
# ════════════════════════════════════════════════════════════════════════════
# جداول الريّ *مُتكرّرة* لا مُطلقة (start_time TIME + duration_min + days_of_week[]؛
# v25_irrigation.sql:43-45) فلا يوجد ``tstzrange`` مفردة يمكن فرض EXCLUDE عليها عبر
# btree_gist — لذا الحارس على مستوى التطبيق (409). نمذجة كلّ جدول كمجموعة فترات على
# دورة أسبوعيّة (7×1440 دقيقة) مع لفّ حول منتصف الليل ونهاية الأسبوع، ثمّ تقاطُع الفترات.

_MIN_PER_DAY = 1440
_MIN_PER_WEEK = 7 * _MIN_PER_DAY


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
