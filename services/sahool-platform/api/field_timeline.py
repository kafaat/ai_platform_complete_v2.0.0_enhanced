"""
api/field_timeline.py — مُجمِّع الخطّ الزمني للحقل (Field Timeline)

المرحلة ١، البند ٧ من خارطة الطريق.

يبني خطّاً زمنيّاً موحّداً (chronological) لكلّ ما حدث على حقل: إنشاء، انتقالات
المراحل، عمليّات (بذر/ري/تسميد/حصاد)، مشاهدات ميدانيّة (pins)، معايرة الإنتاج،
ومطر. هذا نظير FieldView Field Timeline.

تصميم pure (لا DB): يأخذ الأحداث كمُدخَل — نفس نمط event_replay.py الذي وُصِّل
بنجاح. النسخة المُوصَّلة بالـDB (تجلب من events + lifecycle_transitions +
trueup_calibrations) تحتاج PostgreSQL وتُبنى لاحقاً فوق هذا المنطق النقي.

يعيد استخدام البُنى المُختبَرة في data_lineage.py (LineageSourceType،
_summarize_action) بدل تكرارها.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from api.data_lineage import LineageSourceType, _summarize_action


class TimelineCategory(str, Enum):
    """تصنيف بصري لكلّ حدث في الخطّ الزمني (لأيقونات الواجهة العربيّة)."""
    LIFECYCLE = "lifecycle"        # انتقال مرحلة
    OPERATION = "operation"        # بذر/ري/تسميد/حصاد
    OBSERVATION = "observation"    # مشاهدة ميدانيّة (pin)
    CALIBRATION = "calibration"    # معايرة الإنتاج (trueup)
    WEATHER = "weather"            # مطر/طقس مؤثّر
    SYSTEM = "system"              # إنشاء/تحديث


# تخطيط نوع الحدث → الفئة (للأيقونات والترشيح)
_EVENT_CATEGORY: Dict[str, TimelineCategory] = {
    "field.created": TimelineCategory.SYSTEM,
    "field.create": TimelineCategory.SYSTEM,
    "field.updated": TimelineCategory.SYSTEM,
    "field.update": TimelineCategory.SYSTEM,
    "lifecycle.transitioned": TimelineCategory.LIFECYCLE,
    "field.advance_stage": TimelineCategory.LIFECYCLE,
    "operation.planting.start": TimelineCategory.OPERATION,
    "operation.planting.completed": TimelineCategory.OPERATION,
    "operation.irrigation.start": TimelineCategory.OPERATION,
    "operation.irrigation.completed": TimelineCategory.OPERATION,
    "operation.fertilizer.completed": TimelineCategory.OPERATION,
    # L1 FIX: التسمية المعتمدة في event_bus enum هي fertilizer.applied — كانت
    # مفقودة فلا تُصنَّف أحداث التسميد الحقيقيّة (السابق غطّى completed فقط).
    "operation.fertilizer.applied": TimelineCategory.OPERATION,
    "prescription.applied": TimelineCategory.OPERATION,
    "walk_plan.generated": TimelineCategory.OPERATION,
    "operation.harvest.complete": TimelineCategory.OPERATION,
    "operation.harvest.completed": TimelineCategory.OPERATION,
    "scouting.pin.created": TimelineCategory.OBSERVATION,
    "scouting.observation": TimelineCategory.OBSERVATION,
    "trueup.apply": TimelineCategory.CALIBRATION,
    "trueup.applied": TimelineCategory.CALIBRATION,
    "weather.rainfall": TimelineCategory.WEATHER,
}


@dataclass
class TimelineEvent:
    """حدث واحد في الخطّ الزمني."""
    timestamp: str                       # ISO 8601
    event_type: str
    category: TimelineCategory
    summary_ar: str
    actor_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "category": self.category.value,
            "summary_ar": self.summary_ar,
            "actor_id": self.actor_id,
            "payload": self.payload,
        }


@dataclass
class FieldTimeline:
    """الخطّ الزمني الكامل لحقل."""
    field_id: str
    total_events: int
    earliest_at: Optional[str]
    latest_at: Optional[str]
    events: List[TimelineEvent]
    # إحصاءات لكلّ فئة (لشارات الواجهة)
    category_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_id": self.field_id,
            "total_events": self.total_events,
            "earliest_at": self.earliest_at,
            "latest_at": self.latest_at,
            "category_counts": self.category_counts,
            "events": [e.to_dict() for e in self.events],
        }


def _categorize(event_type: str) -> TimelineCategory:
    """يصنّف نوع الحدث؛ الافتراضي SYSTEM لو غير معروف."""
    return _EVENT_CATEGORY.get(event_type, TimelineCategory.SYSTEM)


def _parse_ts(ts: str) -> datetime:
    """يحلّل ISO timestamp بأمان (للترتيب)."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        # لو التوقيت غير صالح، نضعه في الأقدم لئلّا نكسر الترتيب
        return datetime.min


def assemble_timeline(
    field_id: str,
    events: List[Dict[str, Any]],
    *,
    newest_first: bool = True,
    category_filter: Optional[List[str]] = None,
) -> FieldTimeline:
    """يبني خطّاً زمنيّاً من قائمة أحداث.

    كلّ حدث dict يحوي على الأقلّ: event_type، occurred_at (أو timestamp)،
    وعادةً payload و actor_id.

    Args:
        field_id: معرّف الحقل.
        events: أحداث خام (من events table أو مُمرَّرة في الـrequest).
        newest_first: ترتيب تنازلي (الأحدث أوّلاً) — افتراضي للواجهة.
        category_filter: لو معطى، يُبقي فقط هذه الفئات.

    Returns:
        FieldTimeline مرتّب + مُصنّف + بإحصاءات.
    """
    timeline_events: List[TimelineEvent] = []
    category_counts: Dict[str, int] = {}

    for ev in events:
        event_type = ev.get("event_type", "unknown")
        ts = ev.get("occurred_at") or ev.get("timestamp") or ""
        payload = ev.get("payload", {}) or {}
        actor = ev.get("actor_id")

        category = _categorize(event_type)

        # ترشيح بالفئة لو مطلوب
        if category_filter and category.value not in category_filter:
            continue

        summary = _summarize_action(event_type, payload)

        timeline_events.append(
            TimelineEvent(
                timestamp=ts,
                event_type=event_type,
                category=category,
                summary_ar=summary,
                actor_id=actor,
                payload=payload,
            )
        )
        category_counts[category.value] = category_counts.get(category.value, 0) + 1

    # ترتيب زمني
    timeline_events.sort(key=lambda e: _parse_ts(e.timestamp), reverse=newest_first)

    timestamps = [e.timestamp for e in timeline_events if e.timestamp]
    earliest = min(timestamps, key=_parse_ts) if timestamps else None
    latest = max(timestamps, key=_parse_ts) if timestamps else None

    return FieldTimeline(
        field_id=field_id,
        total_events=len(timeline_events),
        earliest_at=earliest,
        latest_at=latest,
        events=timeline_events,
        category_counts=category_counts,
    )
