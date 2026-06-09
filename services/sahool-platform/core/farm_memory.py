"""
sahool_core.farm_memory
=========================
الذاكرة التشغيلية الموحّدة للمزرعة — نقطة استرجاع واحدة لتاريخها الكامل.

الفجوة المسدودة من وثيقة Digital Agriculture OS:
  "ذاكرة تشغيلية للمزرعة" تشمل:
    • ماذا حدث     ← activity_log
    • أين حدث     ← observations + lat/lon
    • لماذا حدث   ← recommendation_replay
    • ما القرار   ← recommendation_log + provenance
    • ما النتيجة  ← outcomes + calibration
    • كيف نُحسّن  ← feedback_closure (مُعدّ)

كل هذه الوحدات موجودة في النواة، لكن لا "view موحّد" يجمعها لمزرعة
واحدة. مهندس يسأل "ماذا حدث في حقل fld_03 خلال 2025؟" يحتاج
استعلامات في 5 جداول مختلفة. هذه الوحدة تحلّ ذلك.

النمط: **Composition not Duplication**.
  • لا نُعيد تخزين أيّ شيء — كل البيانات تبقى في مصادرها
  • نُجمّع عند الطلب (read-time aggregation)
  • تفسير صريح: كل query يحمل reason_ar
  • Tenant isolation مفروض في كل دالّة

التمييز عن الموجود:
  recommendation_replay: forensic لتوصية واحدة
  cross_reference_finder: حالات مشابهة في النظام كلّه
  farm_memory: تاريخ كامل لكيان واحد (حقل/مزرعة)

التمييز الأهمّ: لا "ML insights" — هذا layer قراءة، التفسير
الزراعي يبقى للمهندس. صفر اختراع، صفر "تنبؤ سحري".

التكامل:
  ← يقرأ من activity_log + observations + recommendation_log
  ← يستخدم source_of_truth لـarbitration عند تعدّد المصادر
  → يُغذّي multi_season_analytics بتاريخ نظيف
  → يُغذّي الواجهة (timeline view)
  → يُغذّي feedback_closure حين يُفعَّل
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventKind(str, Enum):
    """نوع الحدث في timeline المزرعة."""
    ACTIVITY = "activity"               # من activity_log
    OBSERVATION = "observation"         # قياس
    RECOMMENDATION = "recommendation"   # توصية صادرة
    OUTCOME = "outcome"                  # نتيجة (حصاد، إلخ)
    CALIBRATION = "calibration"         # معايرة zone_factor
    ALERT = "alert"                      # تنبيه (drift، ملوحة، ...)


@dataclass
class MemoryEvent:
    """حدث واحد في timeline. خفيف، composable."""
    event_id: str
    kind: EventKind
    occurred_at: str                    # ISO datetime
    tenant_id: str
    farm_id: str | None
    field_id: str | None
    summary_ar: str                     # وصف بشري
    payload: dict = field(default_factory=dict)   # تفاصيل كاملة
    source_module: str = ""             # من أيّ وحدة جاء


@dataclass
class FarmMemorySnapshot:
    """لقطة كاملة لذاكرة مزرعة في لحظة معيّنة."""
    tenant_id: str
    farm_id: str
    field_ids: list[str]
    period_from: str
    period_to: str
    total_events: int
    events_by_kind: dict                # {ActivityKind.X: count}
    timeline: list[MemoryEvent]
    open_questions: list[str]           # ما لا نعرفه بعد
    summary_ar: str


# ─── Composition من الوحدات الموجودة ─────────────────────────────

def _activities_to_events(
    activities: list,
    tenant_id: str,
) -> list[MemoryEvent]:
    """يحوّل سجلّ activity_log إلى MemoryEvent.

    صفر اختراع: نمرّر الـpayload كما هو، لا "interpretation" زراعي."""
    events = []
    for a in activities:
        # نتجاهل النشاطات في tenant آخر (Defense in depth)
        if getattr(a, "tenant_id", None) != tenant_id:
            continue

        kind = getattr(a, "kind", "unknown")
        status = getattr(a, "status", "planned")
        # تفسير صريح، لا "AI describes"
        summary = (f"نشاط {kind}: {status}"
                  + (f" — {a.notes_ar}" if getattr(a, "notes_ar", None)
                     else ""))

        events.append(MemoryEvent(
            event_id=getattr(a, "activity_id", f"act_{id(a)}"),
            kind=EventKind.ACTIVITY,
            occurred_at=getattr(a, "planned_for", "") or
                       getattr(a, "completed_at", ""),
            tenant_id=tenant_id,
            farm_id=getattr(a, "farm_id", None),
            field_id=getattr(a, "field_id", None),
            summary_ar=summary,
            payload={"kind": kind, "status": status,
                    "notes": getattr(a, "notes_ar", "")},
            source_module="activity_log",
        ))
    return events


def _observations_to_events(
    observations: list,
    tenant_id: str,
) -> list[MemoryEvent]:
    """يحوّل observations إلى MemoryEvent.

    لا ترشيح للقيم الشاذّة (هذه مهمّة validate_observations).
    لا arbitration هنا (تُستخدم source_of_truth عند الحاجة)."""
    events = []
    for o in observations:
        if getattr(o, "tenant_id", None) != tenant_id:
            continue

        obs_id = getattr(o, "observable_id", "?")
        value = getattr(o, "value", None)
        unit = getattr(o, "unit", "")
        source = getattr(o, "source", "?")
        if hasattr(source, "value"):
            source = source.value

        summary = f"{obs_id} = {value} {unit} ({source})"

        events.append(MemoryEvent(
            event_id=getattr(o, "observation_id", f"obs_{id(o)}"),
            kind=EventKind.OBSERVATION,
            occurred_at=getattr(o, "measured_at", ""),
            tenant_id=tenant_id,
            farm_id=getattr(o, "farm_id", None),
            field_id=getattr(o, "field_id", None),
            summary_ar=summary,
            payload={"observable_id": obs_id, "value": value,
                    "unit": unit, "source": source,
                    "confidence": getattr(o, "confidence", "?")},
            source_module="observations",
        ))
    return events


def _recommendations_to_events(
    recommendations: list,
    tenant_id: str,
) -> list[MemoryEvent]:
    """يحوّل recommendation_log إلى MemoryEvent."""
    events = []
    for r in recommendations:
        if getattr(r, "tenant_id", None) != tenant_id:
            continue

        crop = getattr(r, "crop", "?")
        grade = getattr(r, "quality_grade", "?")
        summary = (f"توصية {crop} ({grade}): "
                  + (getattr(r, "recommendation_ar", "")[:60] or "—"))

        # نوعان من الأحداث: توصية صادرة + نتيجة (إن وُجدت)
        events.append(MemoryEvent(
            event_id=getattr(r, "rec_id", f"rec_{id(r)}"),
            kind=EventKind.RECOMMENDATION,
            occurred_at=getattr(r, "issued_date", ""),
            tenant_id=tenant_id,
            farm_id=getattr(r, "farm_id", None),
            field_id=getattr(r, "zone_id", None) or
                    getattr(r, "field_id", None),
            summary_ar=summary,
            payload={"crop": crop, "grade": grade,
                    "predicted_yield_t_ha": getattr(
                        r, "predicted_yield_t_ha", None)},
            source_module="recommendation_log",
        ))

        # نتيجة الحصاد (إن اكتملت) كحدث منفصل
        actual = getattr(r, "actual_yield_t_ha", None)
        if actual is not None:
            outcome_date = (getattr(r, "outcome_date", None) or
                          getattr(r, "issued_date", ""))
            events.append(MemoryEvent(
                event_id=f"{getattr(r, 'rec_id', 'rec')}_outcome",
                kind=EventKind.OUTCOME,
                occurred_at=outcome_date,
                tenant_id=tenant_id,
                farm_id=getattr(r, "farm_id", None),
                field_id=getattr(r, "zone_id", None) or
                        getattr(r, "field_id", None),
                summary_ar=f"حصاد {crop}: {actual} ط/هـ",
                payload={"actual_yield_t_ha": actual,
                        "predicted_yield_t_ha": getattr(
                            r, "predicted_yield_t_ha", None),
                        "error_pct": getattr(r, "error_pct", None)},
                source_module="recommendation_log",
            ))
    return events


# ─── الـAPI العامّ ───────────────────────────────────────────────

def build_farm_memory(
    *,
    tenant_id: str,
    farm_id: str,
    field_ids: list[str] | None = None,
    activities: list | None = None,
    observations: list | None = None,
    recommendations: list | None = None,
    period_from: str | None = None,
    period_to: str | None = None,
) -> FarmMemorySnapshot:
    """يبني snapshot موحّد لمزرعة.

    Composition strict: لا "AI insights"، فقط جمع وعرض.
    Tenant isolation: كل event يُفلتر بـtenant_id."""

    all_events: list[MemoryEvent] = []

    if activities:
        all_events.extend(_activities_to_events(activities, tenant_id))
    if observations:
        all_events.extend(_observations_to_events(observations, tenant_id))
    if recommendations:
        all_events.extend(_recommendations_to_events(recommendations,
                                                     tenant_id))

    # فلتر farm_id (لو حُدّد field_ids، نفلتر بها أيضاً)
    if field_ids:
        # نقبل: الحدث في farm_id، أو فيه field_id معروف
        all_events = [
            e for e in all_events
            if e.farm_id == farm_id or
            (e.field_id and e.field_id in field_ids)
        ]
    else:
        all_events = [e for e in all_events if e.farm_id == farm_id]

    # فلتر زمني (إن طُلب)
    if period_from:
        all_events = [e for e in all_events
                     if e.occurred_at and e.occurred_at >= period_from]
    if period_to:
        all_events = [e for e in all_events
                     if e.occurred_at and e.occurred_at <= period_to]

    # رتّب زمنياً
    all_events.sort(key=lambda e: e.occurred_at)

    # إحصائيات
    by_kind: dict = {}
    for e in all_events:
        k = e.kind.value
        by_kind[k] = by_kind.get(k, 0) + 1

    # "open questions" — ما لا نعرفه بعد (شفّافية)
    open_q = []
    rec_count = by_kind.get("recommendation", 0)
    outcome_count = by_kind.get("outcome", 0)
    if rec_count > outcome_count:
        gap = rec_count - outcome_count
        open_q.append(f"{gap} توصية لم تُسجَّل نتائجها بعد")
    if not by_kind.get("observation", 0):
        open_q.append("لا مشاهدات/قياسات مسجّلة — التوصيات بلا دليل")
    if not by_kind.get("activity", 0):
        open_q.append("لا أنشطة مسجّلة — لا نعرف ماذا نُفّذ فعلاً")

    # ملخّص
    period_str = ""
    if period_from and period_to:
        period_str = f" بين {period_from[:10]} و {period_to[:10]}"
    summary = (f"المزرعة {farm_id} — {len(all_events)} حدثاً{period_str}. "
              + (f"⚠️ {len(open_q)} سؤال مفتوح" if open_q
                 else "✅ سجلّ مكتمل ضمن النطاق المعروف"))

    return FarmMemorySnapshot(
        tenant_id=tenant_id,
        farm_id=farm_id,
        field_ids=field_ids or [],
        period_from=period_from or "",
        period_to=period_to or "",
        total_events=len(all_events),
        events_by_kind=by_kind,
        timeline=all_events,
        open_questions=open_q,
        summary_ar=summary,
    )


def field_timeline(
    snapshot: FarmMemorySnapshot,
    field_id: str,
) -> list[MemoryEvent]:
    """يستخرج timeline حقل واحد من snapshot المزرعة."""
    return [e for e in snapshot.timeline
            if e.field_id == field_id]


def events_around_recommendation(
    snapshot: FarmMemorySnapshot,
    rec_id: str,
    *,
    days_before: int = 7,
    days_after: int = 30,
) -> list[MemoryEvent]:
    """يستخرج ما حدث حول توصية معيّنة — لتفسير "لماذا فشلت/نجحت".

    مهم للـforensic: مهندس يفحص توصية فاشلة يحتاج رؤية:
      • ما المشاهدات قبلها (الإدخال)
      • ما الأنشطة بعدها (هل نُفّذت؟)
      • ما النتيجة (outcome)"""
    from datetime import timedelta

    rec = next((e for e in snapshot.timeline
               if e.event_id == rec_id and e.kind == EventKind.RECOMMENDATION),
              None)
    if rec is None:
        return []

    try:
        anchor = datetime.fromisoformat(rec.occurred_at[:19])
    except (ValueError, IndexError):
        return [rec]

    before = (anchor - timedelta(days=days_before)).isoformat()
    after = (anchor + timedelta(days=days_after)).isoformat()

    return [e for e in snapshot.timeline
            if before <= e.occurred_at <= after
            and (e.field_id == rec.field_id or e.event_id == rec_id)]


def memory_density_report(snapshot: FarmMemorySnapshot) -> dict:
    """يقيس "كثافة الذاكرة": هل لدينا بيانات كافية لاتخاذ قرار؟

    معايير شفّافة (لا "AI score"):
      • >= 3 توصيات + outcomes = density='high'
      • >= 1 توصية + outcomes = 'medium'
      • أنشطة فقط = 'low'
      • فارغ = 'empty'"""
    by_kind = snapshot.events_by_kind
    rec = by_kind.get("recommendation", 0)
    outcome = by_kind.get("outcome", 0)
    obs = by_kind.get("observation", 0)
    act = by_kind.get("activity", 0)

    if rec >= 3 and outcome >= 3:
        density = "high"
        note = f"بيانات وفيرة ({rec} توصية، {outcome} نتيجة)"
    elif rec >= 1 and outcome >= 1:
        density = "medium"
        note = f"بيانات أوّلية ({rec} توصية، {outcome} نتيجة)"
    elif obs > 0 or act > 0:
        density = "low"
        note = f"بيانات وصفية فقط ({obs} مشاهدة، {act} نشاط)، لا outcomes"
    else:
        density = "empty"
        note = "لا بيانات — تبدأ من الصفر"

    return {
        "density": density,
        "note_ar": note,
        "rec_count": rec,
        "outcome_count": outcome,
        "obs_count": obs,
        "activity_count": act,
        "summary_ar": f"كثافة الذاكرة: {density} — {note}",
    }
