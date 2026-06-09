"""
sahool_core.activity_log
========================
سجلّ أنشطة المزرعة + متابعة المهام (مستلهَم من farmOS Log/Task).

الفجوة المسدودة: الحلقة المغلقة كانت ناقصة. observations يحفظ القياسات
(NDVI=0.5)، لكن لا يحفظ "ما فعله المزارع" (رويت 20مم في 2026-03-15).
implementation_verification يطلب سجلّ تنفيذ موضوعياً — هذه الوحدة
تُغذّيه. وlearning loop يحتاج "نُفّذ/تأخّر/تُجوهل" لتعلّم أنماط التبنّي.

المفاهيم (نظيفة، لا تكرار لما هو موجود):
  • Activity = حدث في المزرعة (ري/رش/تسميد/حصاد/...)
  • Status: planned → in_progress → completed (أو skipped/cancelled)
  • Link: rec_id اختياري يربط النشاط بالتوصية التي ولّدته

نمط farmOS المستلهَم: log entity واحد بأنواع متعدّدة، لا جدول لكل نشاط.
هذا يطابق نمط observations لدينا (جدول واحد + observable_id).

التكامل (دون كسر):
  ← يُحقن من recommendation_engine بعد توليد توصية (planned_task)
  ← يُحدَّث من الواجهة عند تنفيذ المزارع (completed)
  → يغذّي implementation_verification.verify_recommendation_followup
  → يغذّي calibration_loop حين يكتمل الحصاد
  → يغذّي farmer_agency حين يُتجاهَل (skip_reason إشارة تعلّم)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ActivityType(str, Enum):
    IRRIGATION = "irrigation"
    FERTILIZATION = "fertilization"
    PESTICIDE = "pesticide"
    SEEDING = "seeding"
    HARVEST = "harvest"
    PRUNING = "pruning"
    WEEDING = "weeding"
    OBSERVATION = "observation"
    OTHER = "other"


class ActivityStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"  # المزارع تجاوزها عمداً → إشارة لـfarmer_agency


@dataclass
class Activity:
    activity_id: str
    tenant_id: str
    field_id: str
    activity_type: ActivityType
    status: ActivityStatus
    rec_id: str | None = None  # ربط بالتوصية
    planned_date: str | None = None  # ISO date
    completed_date: str | None = None
    quantity: float | None = None
    unit: str | None = None
    notes_ar: str | None = None
    skip_reason: str | None = None
    lon: float | None = None  # Geo-tag اختياري (farmOS pattern)
    lat: float | None = None  # ربط النشاط بزاوية الحقل لا كلّه


def new_activity_id() -> str:
    """معرّف فريد للنشاط (UUID4 مختصر)."""
    return f"act_{uuid.uuid4().hex[:12]}"


def plan_activity_from_recommendation(
    *,
    tenant_id: str,
    field_id: str,
    rec_id: str,
    activity_type: str,
    planned_date: str,
    quantity: float | None = None,
    unit: str | None = None,
    notes_ar: str | None = None,
    lon: float | None = None,
    lat: float | None = None,
) -> Activity:
    """يُحوّل توصية إلى مهمّة مخطّطة. النقطة الأولى في الحلقة المغلقة.

    التوصية من recommendation_engine → مهمّة planned هنا → المزارع
    يُحدّثها (completed/skipped) → implementation_verification يقرأها.
    lon/lat اختياريان (Geo-tag للمهام، farmOS pattern)."""
    try:
        atype = ActivityType(activity_type.lower())
    except ValueError:
        atype = ActivityType.OTHER
    return Activity(
        activity_id=new_activity_id(),
        tenant_id=tenant_id,
        field_id=field_id,
        rec_id=rec_id,
        activity_type=atype,
        status=ActivityStatus.PLANNED,
        planned_date=planned_date,
        quantity=quantity,
        unit=unit,
        notes_ar=notes_ar,
        lon=lon,
        lat=lat,
    )


def mark_completed(
    activity: Activity,
    *,
    completed_date: str | None = None,
    actual_quantity: float | None = None,
    notes_ar: str | None = None,
) -> Activity:
    """يُحدّث المهمّة لمنفّذة. يحفظ الكمّية الفعلية (قد تختلف عن المخطّطة)."""
    activity.status = ActivityStatus.COMPLETED
    activity.completed_date = completed_date or datetime.now().date().isoformat()
    if actual_quantity is not None:
        activity.quantity = actual_quantity
    if notes_ar:
        activity.notes_ar = (activity.notes_ar or "") + "\n" + notes_ar
    return activity


def mark_skipped(activity: Activity, *, reason_ar: str) -> Activity:
    """المزارع تجاوز المهمّة عمداً. السبب إشارة تعلّم لـfarmer_agency.

    إن تكرّر التجاوز لنوع توصية معيّن → النظام يخفض ثقتها (التعلّم
    من الرفض، تماماً كما في farmer_agency.record_farmer_response)."""
    activity.status = ActivityStatus.SKIPPED
    activity.skip_reason = reason_ar
    return activity


# ── الاستعلامات (وظيفية، لا تخمين، لا اختراع) ──


def overdue_activities(activities: list[Activity], *, today: str | None = None) -> list[Activity]:
    """مهام متأخّرة (planned + planned_date < اليوم). مفيد للتذكير."""
    today = today or datetime.now().date().isoformat()
    return [
        a
        for a in activities
        if a.status == ActivityStatus.PLANNED and a.planned_date and a.planned_date < today
    ]


def activities_for_recommendation(activities: list[Activity], rec_id: str) -> list[Activity]:
    """كل الأنشطة المرتبطة بتوصية واحدة (لتغذية implementation_verification)."""
    return [a for a in activities if a.rec_id == rec_id]


def adoption_summary(activities: list[Activity]) -> dict:
    """ملخّص تبنّي المزارع: كم نفّذ، كم تجاوز، كم لم يُلامس.

    يغذّي farmer_agency: نسبة skip عالية لنوع → إشارة لإعادة النظر."""
    if not activities:
        return {"total": 0, "completed": 0, "skipped": 0, "pending": 0, "adoption_rate": None}
    total = len(activities)
    completed = sum(1 for a in activities if a.status == ActivityStatus.COMPLETED)
    skipped = sum(1 for a in activities if a.status == ActivityStatus.SKIPPED)
    pending = sum(
        1 for a in activities if a.status in (ActivityStatus.PLANNED, ActivityStatus.IN_PROGRESS)
    )
    completed_or_skipped = completed + skipped
    rate = round(completed / completed_or_skipped, 2) if completed_or_skipped else None
    return {
        "total": total,
        "completed": completed,
        "skipped": skipped,
        "pending": pending,
        "adoption_rate": rate,
        "note_ar": (
            f"نُفّذ {completed}/{completed + skipped} نشاطاً (معدّل التبنّي {rate:.0%})"
            if rate is not None
            else f"{pending} نشاطاً ينتظر التنفيذ"
        ),
    }
