"""
services/sahool-platform/api/event_replay.py — Event Replay & Causal Tracing

⚠ المستند الخارجي عن Observability ادّعى "Causality Sourced System".
   الواقع: هذا event log + state reconstruction. مفيد، لكن ليس fancy.

ما يفعله:
   ١. يجلب كل events لحقل معيّن (ترتيب زمني)
   ٢. يطبّقها واحدة تلو الأخرى لإعادة بناء الـstate
   ٣. ينتج timeline قابل للعرض للـUI أو الـadmin
   ٤. يحدّد "ما الذي حدث بين تاريخَين"
   ٥. يربط events بـcommands (causal chain)

ما لا يفعله:
   ✗ ML pattern detection
   ✗ "causal AI reasoning"
   ✗ time-travel debugging كما يدّعي المستند

الاستخدامات الحقيقيّة:
   - debugging: "لماذا الحقل في مرحلة GROWING منذ ٤٠ يوم؟"
   - audit:    "من غيّر الـgeometry قبل أسبوع؟"
   - reports:  "كم مرّة رُويَ هذا الحقل في الموسم؟"
   - UI:       "Timeline" view على شاشة Field Detail
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg

from .event_bus import EventBus


# ─── Types ──────────────────────────────────────────────────────

@dataclass
class TimelineEntry:
    """نقطة على الـtimeline."""
    event_id: str
    event_type: str
    occurred_at: str
    source: str
    actor_id: Optional[str]
    command_id: Optional[str]
    summary_ar: str          # وصف مُختصَر بالعربيّة
    payload: Dict[str, Any]


@dataclass
class ReconstructedState:
    """State مُعاد بناؤها من الـevents."""
    entity_id: str
    entity_type: str
    field_name: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    area_ha: Optional[float] = None
    crop: Optional[str] = None
    planting_date: Optional[str] = None
    harvest_date: Optional[str] = None

    irrigation_count: int = 0
    fertilizer_count: int = 0
    pesticide_count: int = 0
    soil_samples_count: int = 0

    last_ndvi: Optional[float] = None
    last_ndvi_date: Optional[str] = None

    last_event_at: Optional[str] = None
    total_events: int = 0


@dataclass
class CausalChain:
    """سلسلة سببيّة: command → events resulted."""
    command_id: str
    command_type: Optional[str]
    triggered_events: List[TimelineEntry]


# ─── Summary helpers (Arabic) ───────────────────────────────────

_EVENT_SUMMARY_AR: Dict[str, str] = {
    "field.created":                  "أُنشئ الحقل",
    "field.updated":                  "حُدِّثت بيانات الحقل",
    "field.geometry_changed":         "تغيّرت حدود الحقل",
    "field.deleted":                  "حُذِف الحقل",
    "lifecycle.transitioned":         "انتقل إلى مرحلة جديدة",
    "operation.planting.started":     "بدأ البذر",
    "operation.planting.completed":   "اكتمل البذر",
    "operation.irrigation.started":   "بدأ الري",
    "operation.irrigation.completed": "اكتمل الري",
    "operation.fertilizer.applied":   "طُبِّق تسميد",
    "operation.pesticide.applied":    "طُبِّق مبيد",
    "operation.harvest.started":      "بدأ الحصاد",
    "operation.harvest.completed":    "اكتمل الحصاد",
    "trueup.applied":                 "معايرة الإنتاج (TrueUp)",
    "remote_sensing.ndvi.observed":   "وصول قراءة NDVI",
    "soil.sample.recorded":           "تسجيل عيّنة تربة",
    "weather.rain":                   "حدث مطر",
    "weather.moisture.low":           "إجهاد مائي",
    "ai.suggestion.generated":        "اقتراح من سهول",
    "ai.anomaly.detected":            "كشف شذوذ",
}


def _summarize_ar(event_type: str, payload: Dict[str, Any]) -> str:
    """يولّد سطر عربي مفهوم لكل event."""
    base = _EVENT_SUMMARY_AR.get(event_type, event_type)

    # إضافات سياقيّة
    if event_type == "lifecycle.transitioned" and "to_stage" in payload:
        stage_ar = {
            "CREATED": "أُنشئ", "PREPARED": "جُهِّز", "PLANTED": "زُرع",
            "GROWING": "ينمو", "MATURE": "ناضج", "HARVESTED": "حُصِد",
            "POST_HARVEST": "ما بعد الحصاد",
        }.get(payload["to_stage"], payload["to_stage"])
        return f"{base}: {stage_ar}"

    if event_type == "operation.irrigation.completed" and "water_m3" in payload:
        return f"{base} ({payload['water_m3']} م³)"

    if event_type == "operation.fertilizer.applied":
        parts = []
        if "nitrogen_kg" in payload: parts.append(f"N={payload['nitrogen_kg']}")
        if "phosphorus_kg" in payload: parts.append(f"P={payload['phosphorus_kg']}")
        if "potassium_kg" in payload: parts.append(f"K={payload['potassium_kg']}")
        if parts:
            return f"{base} ({', '.join(parts)} kg)"

    if event_type == "remote_sensing.ndvi.observed" and "ndvi_mean" in payload:
        return f"{base} (NDVI={payload['ndvi_mean']:.2f})"

    if event_type == "trueup.applied" and "actual_yield_kg_ha" in payload:
        return f"{base} (الإنتاج الفعلي: {payload['actual_yield_kg_ha']} kg/ha)"

    return base


# ─── Reconstruction engine ──────────────────────────────────────

class FieldStateReconstructor:
    """
    يُعيد بناء state حقل من history.

    Pure function logic — يمكن اختباره بدون DB.
    """

    @staticmethod
    def apply_event(state: ReconstructedState, event: Dict[str, Any]) -> ReconstructedState:
        """يطبّق event على state حالي ويُعيد state جديدة."""
        etype = event["event_type"]
        payload = event["payload"] if isinstance(event["payload"], dict) else {}

        state.total_events += 1
        state.last_event_at = event["occurred_at"]

        if etype == "field.created":
            state.field_name = payload.get("name_ar") or payload.get("name")
            state.area_ha = payload.get("area_ha")
            state.crop = payload.get("crop")

        elif etype == "field.updated":
            if "name_ar" in payload: state.field_name = payload["name_ar"]
            if "area_ha" in payload: state.area_ha = payload["area_ha"]
            if "crop" in payload: state.crop = payload["crop"]

        elif etype == "field.geometry_changed":
            if "area_ha" in payload: state.area_ha = payload["area_ha"]

        elif etype == "lifecycle.transitioned":
            new_stage = payload.get("to_stage")
            if new_stage:
                state.lifecycle_stage = new_stage
                if new_stage == "PLANTED":
                    state.planting_date = event["occurred_at"]
                elif new_stage == "HARVESTED":
                    state.harvest_date = event["occurred_at"]

        elif etype == "operation.irrigation.completed":
            state.irrigation_count += 1

        elif etype == "operation.fertilizer.applied":
            state.fertilizer_count += 1

        elif etype == "operation.pesticide.applied":
            state.pesticide_count += 1

        elif etype == "soil.sample.recorded":
            state.soil_samples_count += 1

        elif etype == "remote_sensing.ndvi.observed":
            ndvi = payload.get("ndvi_mean")
            if ndvi is not None:
                state.last_ndvi = ndvi
                state.last_ndvi_date = event["occurred_at"]

        return state

    @classmethod
    def reconstruct(
        cls,
        entity_type: str,
        entity_id: str,
        events: List[Dict[str, Any]],
    ) -> ReconstructedState:
        """يُعيد بناء كامل state من قائمة events مرتّبة زمنياً."""
        state = ReconstructedState(entity_id=entity_id, entity_type=entity_type)
        # Apply in temporal order. tiebreaker للطوابع المتساوية (مراجعة #2):
        # occurred_at ثمّ seq ثمّ event_id → ترتيب حتمي حتّى عند تساوي الوقت
        # (وإلّا عكس ترتيب الإدخال يغيّر الحالة النهائيّة — لا حتميّة).
        sorted_events = sorted(
            events,
            key=lambda e: (e.get("occurred_at", ""),
                           e.get("seq", 0),
                           str(e.get("event_id", ""))),
        )
        for ev in sorted_events:
            state = cls.apply_event(state, ev)
        return state


# ─── Replay API ─────────────────────────────────────────────────

class EventReplay:
    """High-level API لقراءة + تفسير الـevents."""

    def __init__(self, bus: EventBus):
        self.bus = bus

    async def get_timeline(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 100,
    ) -> List[TimelineEntry]:
        """timeline قابل للعرض في الـUI."""
        events = await self.bus.query_entity_history(entity_type, entity_id, limit)
        from api.event_upcasting import upcast
        out = []
        for e in events:
            raw_payload = e["payload"] or {}
            # ترقية المخطّط: أحداث قديمة تُرقّى لأحدث نسخة قبل العرض/البناء
            # (سدّ فجوة حماية إعادة التشغيل) — المخزن يبقى append-only.
            payload, _ver = upcast(e["event_type"], raw_payload,
                                   e.get("schema_version", "1.0"))
            out.append(TimelineEntry(
                event_id=e["event_id"],
                event_type=e["event_type"],
                occurred_at=e["occurred_at"] or "",
                source=e["source"],
                actor_id=e["actor_id"],
                command_id=e["command_id"],
                summary_ar=_summarize_ar(e["event_type"], payload),
                payload=payload,
            ))
        return out

    async def reconstruct_state(
        self,
        entity_type: str,
        entity_id: str,
    ) -> ReconstructedState:
        """يُعيد بناء الـstate الحاليّة من الـhistory."""
        events = await self.bus.query_entity_history(entity_type, entity_id, limit=10000)
        return FieldStateReconstructor.reconstruct(entity_type, entity_id, events)

    async def get_causal_chain(
        self,
        command_id: str,
        pool: "asyncpg.Pool",
    ) -> CausalChain:
        """يرجع كل الـevents الذي ولّدها هذا الـcommand."""
        import uuid
        async with pool.acquire() as conn:
            cmd_row = await conn.fetchrow(
                "SELECT command_type FROM commands WHERE command_id = $1",
                uuid.UUID(command_id),
            )
            event_rows = await conn.fetch(
                """
                SELECT event_id, event_type, payload, source, actor_id,
                       command_id, occurred_at
                FROM events
                WHERE command_id = $1
                ORDER BY occurred_at ASC
                """,
                uuid.UUID(command_id),
            )

        triggered = [
            TimelineEntry(
                event_id=str(r["event_id"]),
                event_type=r["event_type"],
                occurred_at=r["occurred_at"].isoformat() if r["occurred_at"] else "",
                source=r["source"],
                actor_id=r["actor_id"],
                command_id=command_id,
                summary_ar=_summarize_ar(
                    r["event_type"],
                    r["payload"] if isinstance(r["payload"], dict) else {},
                ),
                payload=r["payload"] if isinstance(r["payload"], dict) else {},
            )
            for r in event_rows
        ]

        return CausalChain(
            command_id=command_id,
            command_type=cmd_row["command_type"] if cmd_row else None,
            triggered_events=triggered,
        )
