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

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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
    actor_id: str | None
    command_id: str | None
    summary_ar: str  # وصف مُختصَر بالعربيّة
    payload: dict[str, Any]


@dataclass
class ReconstructedState:
    """State مُعاد بناؤها من الـevents."""

    entity_id: str
    entity_type: str
    field_name: str | None = None
    lifecycle_stage: str | None = None
    area_ha: float | None = None
    crop: str | None = None
    planting_date: str | None = None
    harvest_date: str | None = None

    irrigation_count: int = 0
    fertilizer_count: int = 0
    pesticide_count: int = 0
    soil_samples_count: int = 0

    # عدّادات بدء/إكمال العمليّات (أحداث operation.*.started/completed الحقيقيّة).
    # ملاحظة صدق: أحداث operation.* تُسجَّل في المخزن بـentity_type='activity'
    # (لا 'field') وتحمل field_id في الـpayload؛ فهذه العدّادات تُسقَط حين تُغذّى
    # تلك الأحداث للمُسقِط (مثلاً عند بناء مجرى موحّد للحقل وأنشطته).
    planting_started_count: int = 0
    planting_completed_count: int = 0
    irrigation_started_count: int = 0
    harvest_started_count: int = 0
    harvest_completed_count: int = 0

    # المواسم (أحداث season.created/closed — entity_type='season' في المخزن،
    # تحمل field_id في الـpayload). current_crop يُشتقّ من أوّل محصول في الموسم.
    season_count: int = 0
    season_closed_count: int = 0
    current_crop: str | None = None
    last_sowing_date: str | None = None

    # التنبيهات (alert.created — entity_type='alert'، يحمل field_id).
    alert_count: int = 0
    last_alert_severity: str | None = None
    last_alert_type: str | None = None

    # الحالة القانونيّة الموحّدة (field.state_changed — entity_type='field').
    validity: str | None = None
    execution_mode: str | None = None

    # الأنشطة العامّة (activity.recorded — entity_type='activity', يحمل field_id).
    # هذا حدث ACTIVITY_RECORDED الاحتياطيّ الحقيقيّ (field_aggregate.activity_event_for):
    # يُصدَر حين لا يُطابَق نوع النشاط+حالته أيّ operation.* محدَّد (مثل scouting/عامّ).
    # payload الحقيقيّ: {field_id, season_id, activity_type, status} (routers/fields).
    activity_recorded_count: int = 0
    last_activity_type: str | None = None

    # معايرة الإنتاج (trueup.applied — entity_type='field'). payload الحقيقيّ:
    # {operation_id, k_old, k_new, measured_yield_kg_ha, adjusted_yield_kg_ha,
    # error_pct, moisture_corrected} (trueup.TrueUpEngine). نُسقِط آخر معايرة فقط.
    trueup_count: int = 0
    last_trueup_error_pct: float | None = None
    last_adjusted_yield_kg_ha: float | None = None

    # نشر نتيجة فحص التربة (soil.lab.result.published — entity_type='soil_lab_test'،
    # يحمل field_id). payload الحقيقيّ: {field_id} (routers/fields). يُكمّل
    # soil.sample.recorded (طلب الفحص) بحدث «نُشِرت النتيجة».
    soil_lab_published_count: int = 0

    # الصمّامات (irrigation.valve.* — entity_type='irrigation_valve'، entity_id=valve_id).
    # registered payload: {field_id, valve_type}؛ state_changed payload: {status}
    # (routers/irrigation). نُسقِط آخر حالة صمّام معروفة.
    valve_registered_count: int = 0
    valve_state_changed_count: int = 0
    last_valve_status: str | None = None

    # جداول الريّ (irrigation.schedule.created — entity_type='irrigation_schedule').
    # payload الحقيقيّ: {field_id, valve_id} (routers/irrigation).
    irrigation_schedule_count: int = 0

    # الدورة الزراعيّة (crop_rotation.added — entity_type='crop_rotation').
    # payload الحقيقيّ: {field_id, crop} (routers/fields).
    crop_rotation_count: int = 0
    last_rotation_crop: str | None = None

    # تحديث الموسم (season.updated — entity_type='season'). payload الحقيقيّ:
    # {field_id, changed_fields} (routers/fields). عدّاد تحديثات الموسم فقط.
    season_updated_count: int = 0

    deleted: bool = False

    last_ndvi: float | None = None
    last_ndvi_date: str | None = None

    last_event_at: str | None = None
    total_events: int = 0

    # ── تسلسل/فكّ تسلسل للقطة (snapshot) ────────────────────────────
    # اللقطة **مخبّأ مُشتقّ** (derived cache) لتسريع إعادة البناء؛ ليست مصدر حقيقة.
    # مصدر الحقيقة يبقى مخزن الأحداث append-only. الحقول الإسقاطيّة كلّها تُخزَّن في
    # عمود state JSONB (entity_id/entity_type يُخزَّنان كأعمدة جدول مستقلّة).

    # الحقول التي تنتمي للهويّة (تُخزَّن كأعمدة، لا داخل state JSONB).
    _IDENTITY_FIELDS = ("entity_id", "entity_type")

    def to_snapshot_dict(self) -> dict[str, Any]:
        """يُسلسل الحقول الإسقاطيّة إلى شكل JSONB (نقيّ، حتميّ).

        يستثني حقول الهويّة (entity_id/entity_type) لأنّها تُخزَّن كأعمدة الجدول.
        مدفوع بحقول الـdataclass، فيبقى صحيحاً عند إضافة حقول إسقاط جديدة.
        """
        from dataclasses import fields as _dc_fields

        return {
            f.name: getattr(self, f.name)
            for f in _dc_fields(self)
            if f.name not in self._IDENTITY_FIELDS
        }

    @classmethod
    def from_snapshot(cls, row: dict[str, Any]) -> ReconstructedState:
        """يُعيد بناء state من صفّ لقطة (entity_type/entity_id + state JSONB).

        نقيّ — لا I/O. يقبل صفّاً يحوي entity_type/entity_id والحقل state (قاموس
        أو نصّ JSON). المفاتيح غير المعروفة تُتجاهَل (توافق أمام/خلف الإصدارات).
        """
        import json as _json
        from dataclasses import fields as _dc_fields

        raw_state = row.get("state") or {}
        if isinstance(raw_state, str):
            raw_state = _json.loads(raw_state) if raw_state else {}

        known = {f.name for f in _dc_fields(cls)}
        kwargs: dict[str, Any] = {
            "entity_id": str(row["entity_id"]),
            "entity_type": str(row["entity_type"]),
        }
        for key, val in raw_state.items():
            if key in known and key not in cls._IDENTITY_FIELDS:
                kwargs[key] = val
        return cls(**kwargs)


@dataclass
class SnapshotCursor:
    """موضع اللقطة في مجرى الأحداث — الحدّ الفاصل لإعادة البناء التزايديّة.

    المخزن لا يملك عمود seq على جدول events (راجع v11_events_bus)، فالمؤشّر
    الحتميّ هو (occurred_at, event_id): نُعيد تشغيل الأحداث الواقعة **بعد** هذا
    المؤشّر فقط فوق اللقطة. last_seq محفوظ للتوافق مع مخطّط الجدول (قد يكون None).
    """

    last_event_id: str | None
    last_occurred_at: str | None
    last_seq: int | None
    total_events: int

    def is_after(self, event: dict[str, Any]) -> bool:
        """هل هذا الحدث **بعد** المؤشّر؟

        مفتاح الترتيب الحتميّ الرسميّ (v63) هو (occurred_at, seq) — seq مؤشّر
        إدراج تسلسليّ صارم يكسر تعادل occurred_at. نستعمله متى توفّر في طرفَي
        المقارنة (المؤشّر والحدث). تراجُع متوافق رجعيّاً إلى (occurred_at,
        event_id) للقطات القديمة المحفوظة قبل v63 (حيث last_seq=NULL) أو لأحداث
        قديمة بلا seq — يحفظ السلوك السابق دون كسر.
        """
        if self.last_occurred_at is None:
            return True
        ev_occurred = event.get("occurred_at") or ""
        ev_seq = event.get("seq")
        # المسار الحتميّ: كلا الطرفين يملك seq → قارن (occurred_at, seq).
        if self.last_seq is not None and ev_seq is not None:
            return (ev_occurred, ev_seq) > (self.last_occurred_at, self.last_seq)
        # تراجُع متوافق رجعيّاً: (occurred_at, event_id) كما قبل v63.
        ev_id = str(event.get("event_id", ""))
        return (ev_occurred, ev_id) > (self.last_occurred_at, self.last_event_id or "")


@dataclass
class CausalChain:
    """سلسلة سببيّة: command → events resulted."""

    command_id: str
    command_type: str | None
    triggered_events: list[TimelineEntry]


# ─── Summary helpers (Arabic) ───────────────────────────────────

_EVENT_SUMMARY_AR: dict[str, str] = {
    "field.created": "أُنشئ الحقل",
    "field.updated": "حُدِّثت بيانات الحقل",
    "field.geometry_changed": "تغيّرت حدود الحقل",
    "field.deleted": "حُذِف الحقل",
    "lifecycle.transitioned": "انتقل إلى مرحلة جديدة",
    "operation.planting.started": "بدأ البذر",
    "operation.planting.completed": "اكتمل البذر",
    "operation.irrigation.started": "بدأ الري",
    "operation.irrigation.completed": "اكتمل الري",
    "operation.fertilizer.applied": "طُبِّق تسميد",
    "operation.pesticide.applied": "طُبِّق مبيد",
    "operation.harvest.started": "بدأ الحصاد",
    "operation.harvest.completed": "اكتمل الحصاد",
    "trueup.applied": "معايرة الإنتاج (TrueUp)",
    "activity.recorded": "تسجيل عمليّة حقليّة",
    "season.updated": "حُدِّث الموسم",
    "irrigation.valve.registered": "سُجِّل صمّام ريّ",
    "irrigation.valve.state_changed": "تغيّرت حالة الصمّام",
    "irrigation.schedule.created": "أُنشئ جدول ريّ",
    "crop_rotation.added": "أُضيفت دورة زراعيّة",
    "remote_sensing.ndvi.observed": "وصول قراءة NDVI",
    "soil.sample.recorded": "تسجيل عيّنة تربة",
    "soil.lab.result.published": "نُشِرت نتيجة فحص التربة",
    "weather.rain": "حدث مطر",
    "weather.moisture.low": "إجهاد مائي",
    "ai.suggestion.generated": "اقتراح من سهول",
    "ai.anomaly.detected": "كشف شذوذ",
}


def _summarize_ar(event_type: str, payload: dict[str, Any]) -> str:
    """يولّد سطر عربي مفهوم لكل event."""
    base = _EVENT_SUMMARY_AR.get(event_type, event_type)

    # إضافات سياقيّة
    if event_type == "lifecycle.transitioned" and "to_stage" in payload:
        stage_ar = {
            "CREATED": "أُنشئ",
            "PREPARED": "جُهِّز",
            "PLANTED": "زُرع",
            "GROWING": "ينمو",
            "MATURE": "ناضج",
            "HARVESTED": "حُصِد",
            "POST_HARVEST": "ما بعد الحصاد",
        }.get(payload["to_stage"], payload["to_stage"])
        return f"{base}: {stage_ar}"

    if event_type == "operation.irrigation.completed" and "water_m3" in payload:
        return f"{base} ({payload['water_m3']} م³)"

    if event_type == "operation.fertilizer.applied":
        parts = []
        if "nitrogen_kg" in payload:
            parts.append(f"N={payload['nitrogen_kg']}")
        if "phosphorus_kg" in payload:
            parts.append(f"P={payload['phosphorus_kg']}")
        if "potassium_kg" in payload:
            parts.append(f"K={payload['potassium_kg']}")
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
    def apply_event(state: ReconstructedState, event: dict[str, Any]) -> ReconstructedState:
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
            if "name_ar" in payload:
                state.field_name = payload["name_ar"]
            if "area_ha" in payload:
                state.area_ha = payload["area_ha"]
            if "crop" in payload:
                state.crop = payload["crop"]

        elif etype == "field.geometry_changed":
            if "area_ha" in payload:
                state.area_ha = payload["area_ha"]

        elif etype == "field.deleted":
            # payload الحقيقيّ: {name, crop, farm_id} (main._delete_field). نسجّل
            # الحذف كعَلَم (المخزن append-only؛ لا نمحو الحقول المُعاد بناؤها).
            state.deleted = True

        elif etype == "field.state_changed":
            # payload الحقيقيّ: {validity, execution_mode, trigger}
            # (main + field_state_projection). entity_type='field'.
            if "validity" in payload:
                state.validity = payload["validity"]
            if "execution_mode" in payload:
                state.execution_mode = payload["execution_mode"]

        elif etype == "lifecycle.transitioned":
            new_stage = payload.get("to_stage")
            if new_stage:
                state.lifecycle_stage = new_stage
                if new_stage == "PLANTED":
                    state.planting_date = event["occurred_at"]
                elif new_stage == "HARVESTED":
                    state.harvest_date = event["occurred_at"]

        elif etype == "operation.planting.started":
            state.planting_started_count += 1

        elif etype == "operation.planting.completed":
            state.planting_completed_count += 1
            # إكمال البذر يُثبت تاريخ الزراعة من زمن الحدث (لا مفتاح تاريخ في
            # payload النشاط الحقيقيّ: {field_id, season_id, activity_type, status}).
            state.planting_date = event["occurred_at"]

        elif etype == "operation.irrigation.started":
            state.irrigation_started_count += 1

        elif etype == "operation.irrigation.completed":
            state.irrigation_count += 1

        elif etype == "operation.fertilizer.applied":
            state.fertilizer_count += 1

        elif etype == "operation.pesticide.applied":
            state.pesticide_count += 1

        elif etype == "operation.harvest.started":
            state.harvest_started_count += 1

        elif etype == "operation.harvest.completed":
            state.harvest_completed_count += 1
            state.harvest_date = event["occurred_at"]

        elif etype == "season.created":
            # payload الحقيقيّ: {field_id, crops, cultivar, irrigation_type,
            # sowing_date} (main._create_season). crops قائمة محاصيل.
            state.season_count += 1
            crops = payload.get("crops")
            if isinstance(crops, list) and crops:
                state.current_crop = crops[0]
            elif isinstance(crops, str) and crops:
                state.current_crop = crops
            if payload.get("sowing_date"):
                state.last_sowing_date = payload["sowing_date"]

        elif etype == "season.closed":
            state.season_closed_count += 1

        elif etype == "season.updated":
            # payload الحقيقيّ: {field_id, changed_fields} (routers/fields._update_season).
            # حدث تحديث الموسم — نعدّه فقط (لا محصول/تاريخ في الحمولة، لا اشتقاق زائف).
            state.season_updated_count += 1

        elif etype == "activity.recorded":
            # payload الحقيقيّ: {field_id, season_id, activity_type, status}
            # (routers/fields، حدث ACTIVITY_RECORDED الاحتياطيّ). نشاط عامّ لا يُطابَق
            # operation.* محدَّداً (مثل scouting). نعدّه ونحفظ آخر نوع نشاط.
            state.activity_recorded_count += 1
            if "activity_type" in payload:
                state.last_activity_type = payload["activity_type"]

        elif etype == "trueup.applied":
            # payload الحقيقيّ: {operation_id, k_old, k_new, measured_yield_kg_ha,
            # adjusted_yield_kg_ha, error_pct, moisture_corrected} (trueup.TrueUpEngine).
            state.trueup_count += 1
            if "error_pct" in payload:
                state.last_trueup_error_pct = payload["error_pct"]
            if "adjusted_yield_kg_ha" in payload:
                state.last_adjusted_yield_kg_ha = payload["adjusted_yield_kg_ha"]

        elif etype == "soil.lab.result.published":
            # payload الحقيقيّ: {field_id} (routers/fields._update_soil_test عند النشر).
            # يُكمّل soil.sample.recorded (الطلب) بحدث «نُشِرت النتيجة».
            state.soil_lab_published_count += 1

        elif etype == "irrigation.valve.registered":
            # payload الحقيقيّ: {field_id, valve_type} (routers/irrigation.register_valve).
            state.valve_registered_count += 1

        elif etype == "irrigation.valve.state_changed":
            # payload الحقيقيّ: {status} (routers/irrigation.set_valve_state).
            state.valve_state_changed_count += 1
            if "status" in payload:
                state.last_valve_status = payload["status"]

        elif etype == "irrigation.schedule.created":
            # payload الحقيقيّ: {field_id, valve_id} (routers/irrigation.create_schedule).
            state.irrigation_schedule_count += 1

        elif etype == "crop_rotation.added":
            # payload الحقيقيّ: {field_id, crop} (routers/fields.add_crop_rotation).
            state.crop_rotation_count += 1
            if "crop" in payload:
                state.last_rotation_crop = payload["crop"]

        elif etype == "alert.created":
            # payload الحقيقيّ: {severity, alert_type, field_id} (main + event_catalog).
            state.alert_count += 1
            if "severity" in payload:
                state.last_alert_severity = payload["severity"]
            if "alert_type" in payload:
                state.last_alert_type = payload["alert_type"]

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
        events: list[dict[str, Any]],
    ) -> ReconstructedState:
        """يُعيد بناء كامل state من قائمة events مرتّبة زمنياً."""
        state = ReconstructedState(entity_id=entity_id, entity_type=entity_type)
        # Apply in temporal order. tiebreaker للطوابع المتساوية (مراجعة #2):
        # occurred_at ثمّ seq ثمّ event_id → ترتيب حتمي حتّى عند تساوي الوقت
        # (وإلّا عكس ترتيب الإدخال يغيّر الحالة النهائيّة — لا حتميّة).
        sorted_events = sorted(events, key=cls._event_sort_key)
        for ev in sorted_events:
            state = cls.apply_event(state, ev)
        return state

    # ترتيب حتمي مشترك (full replay + incremental): occurred_at ثمّ seq ثمّ
    # event_id. seq أُضيف على جدول events في v63 (BIGINT IDENTITY) — صار التيبريكر
    # الفعليّ حتميّاً صارماً عند تصادم occurred_at. للقطات/أحداث ما قبل v63 (seq
    # غائب) يؤول لـ0 ويبقى event_id كاسر التعادل (توافق رجعيّ). مُستخرَج كي
    # يتطابق المساران (full + incremental) حرفيّاً.
    @staticmethod
    def _event_sort_key(e: dict[str, Any]) -> tuple[str, int, str]:
        return (e.get("occurred_at") or "", e.get("seq") or 0, str(e.get("event_id", "")))

    @classmethod
    def apply_incremental(
        cls,
        base: ReconstructedState,
        events: list[dict[str, Any]],
        cursor: SnapshotCursor | None = None,
    ) -> ReconstructedState:
        """يُطبّق events **بعد** المؤشّر فوق state أساس (لقطة) — نقيّ حتميّ.

        يُرتّب الأحداث بنفس مفتاح reconstruct، ويتخطّى ما لم يتجاوز المؤشّر، ثمّ
        يطبّق الباقي. النتيجة == full replay على كامل المجرى (يُثبته الاختبار
        snapshot-at-k + replay-rest == full replay).
        """
        for ev in sorted(events, key=cls._event_sort_key):
            if cursor is not None and not cursor.is_after(ev):
                continue
            base = cls.apply_event(base, ev)
        return base

    @staticmethod
    def cursor_of(state: ReconstructedState, events: list[dict[str, Any]]) -> SnapshotCursor:
        """يحسب مؤشّر اللقطة لـstate مبنيّة من events (آخر حدث بالترتيب الحتميّ).

        يُمكِّن حفظ لقطة state مع حدّها الفاصل كي تُستأنف إعادة البناء منه.
        """
        if not events:
            return SnapshotCursor(
                last_event_id=None,
                last_occurred_at=state.last_event_at,
                last_seq=None,
                total_events=state.total_events,
            )
        last = max(events, key=FieldStateReconstructor._event_sort_key)
        return SnapshotCursor(
            last_event_id=str(last.get("event_id", "")) or None,
            last_occurred_at=last.get("occurred_at") or state.last_event_at,
            last_seq=last.get("seq"),
            total_events=state.total_events,
        )


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
    ) -> list[TimelineEntry]:
        """timeline قابل للعرض في الـUI."""
        events = await self.bus.query_entity_history(entity_type, entity_id, limit)
        from api.event_upcasting import upcast

        out = []
        for e in events:
            raw_payload = e["payload"] or {}
            # ترقية المخطّط: أحداث قديمة تُرقّى لأحدث نسخة قبل العرض/البناء
            # (سدّ فجوة حماية إعادة التشغيل) — المخزن يبقى append-only.
            payload, _ver = upcast(e["event_type"], raw_payload, e.get("schema_version", "1.0"))
            out.append(
                TimelineEntry(
                    event_id=e["event_id"],
                    event_type=e["event_type"],
                    occurred_at=e["occurred_at"] or "",
                    source=e["source"],
                    actor_id=e["actor_id"],
                    command_id=e["command_id"],
                    summary_ar=_summarize_ar(e["event_type"], payload),
                    payload=payload,
                )
            )
        return out

    async def reconstruct_state(
        self,
        entity_type: str,
        entity_id: str,
    ) -> ReconstructedState:
        """يُعيد بناء الـstate الحاليّة من الـhistory (إعادة تشغيل كاملة دائماً)."""
        events = await self.bus.query_entity_history(entity_type, entity_id, limit=10000)
        return FieldStateReconstructor.reconstruct(entity_type, entity_id, events)

    # ── مسار اللقطة (snapshot-aware) ────────────────────────────────
    # اللقطة مخبّأ مُشتقّ (derived cache): تُسرّع إعادة البناء بإعادة تشغيل
    # الأحداث الواقعة **بعد** مؤشّر اللقطة فقط. مخزن الأحداث append-only يبقى
    # مصدر الحقيقة الوحيد؛ حذف اللقطات لا يفقد بيانات (يُعاد بناؤها كاملةً).

    async def _load_latest_snapshot(
        self,
        entity_type: str,
        entity_id: str,
    ) -> dict[str, Any] | None:
        """يجلب أحدث لقطة لـ(entity_type, entity_id) إن وُجدت، وإلّا None.

        I/O رقيق يحاكي query_entity_history (اتّصال من _acquire للـbus، RLS مُطبَّق
        عبر app.current_tenant حين يُمرَّر conn). الجدول field_state_snapshots (v60).
        """
        async with self.bus._acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT entity_type, entity_id, state, last_event_id,
                       last_occurred_at, last_seq, total_events
                FROM field_state_snapshots
                WHERE entity_type = $1 AND entity_id = $2
                ORDER BY last_occurred_at DESC NULLS LAST, id DESC
                LIMIT 1
                """,
                entity_type,
                entity_id,
            )
        if row is None:
            return None
        return dict(row)

    async def reconstruct_with_snapshot(
        self,
        entity_type: str,
        entity_id: str,
    ) -> ReconstructedState:
        """إعادة بناء مدعومة باللقطة: لقطة (إن وُجدت) + إعادة تشغيل ما بعدها فقط.

        إن لا لقطة → إعادة تشغيل كاملة (سلوك reconstruct_state الحالي حرفيّاً).
        النتيجة مطابقة لإعادة التشغيل الكاملة (تضمنه الاختبارات النقيّة).
        """
        snap_row = await self._load_latest_snapshot(entity_type, entity_id)

        if snap_row is None:
            # لا لقطة — إعادة تشغيل كاملة (السلوك الحاليّ).
            events = await self.bus.query_entity_history(entity_type, entity_id, limit=10000)
            return FieldStateReconstructor.reconstruct(entity_type, entity_id, events)

        base = ReconstructedState.from_snapshot(snap_row)
        cursor = SnapshotCursor(
            last_event_id=str(snap_row["last_event_id"]) if snap_row["last_event_id"] else None,
            last_occurred_at=(
                snap_row["last_occurred_at"].isoformat()
                if hasattr(snap_row["last_occurred_at"], "isoformat")
                else snap_row["last_occurred_at"]
            ),
            last_seq=snap_row.get("last_seq"),
            total_events=snap_row.get("total_events") or 0,
        )
        events = await self.bus.query_entity_history(entity_type, entity_id, limit=10000)
        return FieldStateReconstructor.apply_incremental(base, events, cursor)

    async def save_snapshot(
        self,
        tenant_id: str,
        state: ReconstructedState,
        cursor: SnapshotCursor,
    ) -> None:
        """يحفظ/يحدّث لقطة (upsert على (tenant_id, entity_type, entity_id)).

        I/O رقيق. اللقطة مخبّأ مُشتقّ (لا تمسّ المخزن append-only). الكتابة
        idempotent عبر ON CONFLICT — تُحدّث الحالة والمؤشّر لأحدث ما حُسب.
        """
        import json as _json
        import uuid as _uuid

        async with self.bus._acquire() as conn:
            await conn.execute(
                """
                INSERT INTO field_state_snapshots (
                    tenant_id, entity_type, entity_id, state,
                    last_event_id, last_occurred_at, last_seq, total_events
                ) VALUES ($1::uuid, $2, $3, $4::jsonb, $5, $6::timestamptz, $7, $8)
                ON CONFLICT (tenant_id, entity_type, entity_id) DO UPDATE SET
                    state            = EXCLUDED.state,
                    last_event_id    = EXCLUDED.last_event_id,
                    last_occurred_at = EXCLUDED.last_occurred_at,
                    last_seq         = EXCLUDED.last_seq,
                    total_events     = EXCLUDED.total_events,
                    created_at       = NOW()
                """,
                _uuid.UUID(tenant_id),
                state.entity_type,
                state.entity_id,
                _json.dumps(state.to_snapshot_dict()),
                _uuid.UUID(cursor.last_event_id) if cursor.last_event_id else None,
                cursor.last_occurred_at,
                cursor.last_seq,
                cursor.total_events,
            )

    async def get_causal_chain(
        self,
        command_id: str,
        pool: asyncpg.Pool,
    ) -> CausalChain:
        """يرجع كل الـevents الذي ولّدها هذا الـcommand.

        مسار إداريّ/إعادة بناء عابر للمستأجِرين بالتصميم (يكتسب اتّصاله الخاصّ من
        الـpool ولا يُضبط app.current_tenant). تحت الدور المُقيَّد (NOBYPASSRLS/FORCE
        RLS) يحتاج دوراً خدميّاً مخصّصاً (BYPASSRLS) — متابعة نشر، لا تغيير سلوك.
        """
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
