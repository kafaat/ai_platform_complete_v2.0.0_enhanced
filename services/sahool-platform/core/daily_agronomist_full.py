"""Daily AI Agronomist briefing at farm, field, and zone scopes.

The brief is a presentation layer over Canonical Field State, tasks, alerts, and
operations.  It never turns RAG/KG annotations into recommendations and never
creates prescriptions directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Scope = Literal["farm", "field", "zone"]
Severity = Literal["info", "watch", "action", "critical"]


@dataclass(frozen=True)
class BriefSignal:
    name: str
    severity: Severity
    message_ar: str
    evidence: str = "state"
    due_hours: int | None = None


@dataclass(frozen=True)
class DailyBrief:
    scope: Scope
    scope_id: str
    headline_ar: str
    overnight_changes_ar: list[str]
    actions_today_ar: list[str]
    risks_ar: list[str]
    blocked_ar: list[str]
    confidence: str
    source: str = "canonical_field_state"

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class FieldBriefInput:
    field_id: str
    crop: str
    field_state: dict
    signals: list[BriefSignal] = field(default_factory=list)
    tasks_due: list[str] = field(default_factory=list)
    equipment_alerts: list[str] = field(default_factory=list)
    rag_annotations: list[str] = field(default_factory=list)


def build_field_brief(inp: FieldBriefInput) -> DailyBrief:
    actions: list[str] = []
    risks: list[str] = []
    blocked: list[str] = []
    changes: list[str] = []

    lifecycle = str(
        inp.field_state.get("lifecycle", inp.field_state.get("state", "LIMITED"))
    ).upper()
    confidence = str(inp.field_state.get("confidence", "low"))

    for sig in inp.signals:
        if sig.severity in {"action", "critical"}:
            actions.append(sig.message_ar)
        elif sig.severity == "watch":
            risks.append(sig.message_ar)
        else:
            changes.append(sig.message_ar)
    actions.extend(inp.tasks_due[:5])
    risks.extend(inp.equipment_alerts[:5])

    if lifecycle == "BLOCKED":
        blocked.append("الحقل محجوب عن التوصيات الدقيقة بسبب نقص دليل حاكم.")
    if inp.rag_annotations:
        changes.append("توجد معرفة مرجعية داعمة، لكنها لا تُستخدم وحدها كقرار.")

    headline = _headline(inp.field_id, actions, risks, blocked)
    return DailyBrief(
        scope="field",
        scope_id=inp.field_id,
        headline_ar=headline,
        overnight_changes_ar=changes or ["لا توجد تغيرات مؤكدة كافية خلال آخر دورة."],
        actions_today_ar=actions
        or ["لا يوجد إجراء إلزامي اليوم؛ راقب الحقل واستكمل البيانات الناقصة."],
        risks_ar=risks or ["لا توجد مخاطر عالية مؤكدة."],
        blocked_ar=blocked,
        confidence=confidence,
    )


def build_farm_brief(farm_id: str, field_briefs: list[DailyBrief]) -> DailyBrief:
    actions = [
        f"{b.scope_id}: {a}"
        for b in field_briefs
        for a in b.actions_today_ar
        if "لا يوجد إجراء" not in a
    ]
    risks = [f"{b.scope_id}: {r}" for b in field_briefs for r in b.risks_ar if "لا توجد" not in r]
    blocked = [f"{b.scope_id}: {x}" for b in field_briefs for x in b.blocked_ar]
    critical_count = len(actions) + len(blocked)
    headline = (
        f"لديك {critical_count} أولوية تشغيلية اليوم على مستوى المزرعة."
        if critical_count
        else "لا توجد أولويات حرجة مؤكدة اليوم على مستوى المزرعة."
    )
    return DailyBrief(
        scope="farm",
        scope_id=farm_id,
        headline_ar=headline,
        overnight_changes_ar=[f"تم تلخيص {len(field_briefs)} حقول من مصدر الحقيقة الموحد."],
        actions_today_ar=actions[:10] or ["لا يوجد إجراء إلزامي مؤكد اليوم."],
        risks_ar=risks[:10] or ["لا توجد مخاطر عالية مؤكدة."],
        blocked_ar=blocked[:10],
        confidence=_aggregate_confidence([b.confidence for b in field_briefs]),
    )


def build_zone_brief(
    field_id: str, zone_id: str, zone_state: dict, signals: list[BriefSignal]
) -> DailyBrief:
    field_input = FieldBriefInput(
        field_id=f"{field_id}/{zone_id}",
        crop=str(zone_state.get("crop", "unknown")),
        field_state=zone_state,
        signals=signals,
    )
    brief = build_field_brief(field_input)
    return DailyBrief(
        scope="zone",
        scope_id=f"{field_id}/{zone_id}",
        headline_ar=brief.headline_ar,
        overnight_changes_ar=brief.overnight_changes_ar,
        actions_today_ar=brief.actions_today_ar,
        risks_ar=brief.risks_ar,
        blocked_ar=brief.blocked_ar,
        confidence=brief.confidence,
    )


def _headline(scope_id: str, actions: list[str], risks: list[str], blocked: list[str]) -> str:
    if blocked:
        return f"{scope_id}: لا تصدر توصية دقيقة قبل استكمال الدليل الحاكم."
    if actions:
        return f"{scope_id}: يوجد {len(actions)} إجراء مطلوب اليوم."
    if risks:
        return f"{scope_id}: توجد {len(risks)} مخاطر تحتاج مراقبة."
    return f"{scope_id}: الحالة مستقرة ولا يوجد إجراء مؤكد اليوم."


def _aggregate_confidence(values: list[str]) -> str:
    order = {"none": 0, "low": 1, "medium": 2, "high": 3}
    if not values:
        return "none"
    return min(values, key=lambda v: order.get(v, 0))
