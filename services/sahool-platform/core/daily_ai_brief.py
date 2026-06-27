"""Daily AI Agronomist brief generator.

The brief compresses field-state signals into action items. It does not bypass
Recommendation Engine; it summarizes already-computed state, risks, tasks, and
review statuses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DailyBriefItem:
    priority: str
    title_ar: str
    reason_ar: str
    action_ar: str
    source: str


@dataclass(frozen=True)
class DailyBrief:
    field_id: str
    headline_ar: str
    items: list[DailyBriefItem]
    blocked: list[str] = field(default_factory=list)

    def as_artifact(self) -> dict[str, Any]:
        return {
            "artifact_type": "daily_ai_brief",
            "field_id": self.field_id,
            "headline_ar": self.headline_ar,
            "items": [item.__dict__ for item in self.items],
            "blocked": self.blocked,
        }


def build_daily_ai_brief(
    *,
    field_id: str,
    field_state: dict[str, Any],
    weather_alerts: list[str] | None = None,
    tasks_due: list[dict[str, Any]] | None = None,
    equipment_alerts: list[str] | None = None,
    review_queue_count: int = 0,
) -> DailyBrief:
    items: list[DailyBriefItem] = []
    blocked: list[str] = []

    irrigation = field_state.get("irrigation_state")
    if irrigation in {"due", "high_risk", "needed"}:
        items.append(
            DailyBriefItem(
                priority="high",
                title_ar="الري أولوية اليوم",
                reason_ar="حالة الحقل تشير إلى احتياج مائي أو خطر إجهاد.",
                action_ar="راجع توصية الري المعتمدة ولا تُنشئ وصفة جديدة دون المرور بمحرك التوصية.",
                source="canonical_field_state",
            )
        )

    salinity = field_state.get("salinity_risk")
    if salinity in {"high", "critical"}:
        items.append(
            DailyBriefItem(
                priority="high",
                title_ar="خطر ملوحة يحتاج متابعة",
                reason_ar="إشارة/دليل الملوحة مرتفع داخل حالة الحقل.",
                action_ar="تحقق من EC التربة ومياه الري قبل أي توصية تسميد دقيقة.",
                source="canonical_field_state",
            )
        )

    for alert in weather_alerts or []:
        items.append(
            DailyBriefItem(
                priority="medium",
                title_ar="تنبيه طقس",
                reason_ar=alert,
                action_ar="عدّل توقيت الرش/الري حسب نافذة التشغيل الآمنة.",
                source="weather_signal",
            )
        )

    for task in tasks_due or []:
        items.append(
            DailyBriefItem(
                priority="medium",
                title_ar=f"مهمة مستحقة: {task.get('title', 'مهمة')}",
                reason_ar="المهمة مرتبطة بالحقل أو الجدول اليومي.",
                action_ar="أكمل المهمة من تطبيق المهام وارفع إثبات التنفيذ.",
                source="task_service",
            )
        )

    for alert in equipment_alerts or []:
        items.append(
            DailyBriefItem(
                priority="medium",
                title_ar="تنبيه معدات",
                reason_ar=alert,
                action_ar="افحص المعدة قبل إرسال مهمة تشغيلية.",
                source="equipment_signal",
            )
        )

    if review_queue_count:
        items.append(
            DailyBriefItem(
                priority="medium",
                title_ar="توصيات بانتظار المراجعة",
                reason_ar=f"يوجد {review_queue_count} توصية تحتاج اعتماد مهندس.",
                action_ar="افتح قائمة المراجعة قبل نشرها للمزارع.",
                source="human_review",
            )
        )

    if not field_state.get("has_lab", False):
        blocked.append("التسميد الدقيق محجوب حتى إدخال تحليل تربة/مياه موثوق")

    headline = "لا توجد إجراءات حرجة اليوم" if not items else f"لديك {len(items)} إجراء/تنبيه اليوم"
    return DailyBrief(field_id=field_id, headline_ar=headline, items=items, blocked=blocked)
