"""services/sahool-platform/api/event_catalog.py — سجلّ أنواع أحداث النطاق (Event Catalog).

المشكلة: أسماء أنواع أحداث النطاق (event types) منثورة كسلاسل حرفيّة عبر نداءات
`_emit_domain_event(...)` في `main.py` — فلا مصدر واحد يصف ما هي الأحداث، ولا
إصدار (version) ولا حوكمة (governance) لها.

ما يفعله هذا الملف: يجمع كلّ نوع حدث نطاق في **مصدر واحد للحقيقة** (single source of
truth) — يُعرَّف مرّة واحدة باسمه وإصداره وفئته ووصفه وأبرز حقول حمولته. هكذا:

  • الإصدار (versioning): حقل `version` يسمح بتطوّر شكل الحمولة عبر الزمن دون لبس.
  • الحوكمة (governance): مَن يُصدِر/يستهلك حدثاً ينبغي أن يرجع إلى هذا السجلّ؛ وإصدار
    نوع غير مسجَّل يمكن وسمُه لاحقاً في فحص lint/اختبار CI.

هذا الملفّ **نقيّ** تماماً: لا قاعدة بيانات ولا شبكة — بيانات وصفيّة (metadata) فقط.

حارس الاكتمال (C-15/C-07): `tests/test_event_catalog_completeness.py` يفرض أنّ كلّ عضو
في `EventType` (api/event_bus.py) إمّا مسجَّل هنا وإمّا في قائمة صريحة للأنواع المحجوزة
بلا مُصدِر (بسبب لكلّ مدخل)، وأنّ كلّ نوع في تلك القائمة لا مُصدِر له فعلاً في الشجرة.
الأسماء والحقول أدناه مأخوذة ممّا يُصدَر فعلاً (main.py والراوترات ووحدات api/) — لا اختراع.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DomainEvent:
    """وصف نوع حدث نطاق واحد (تعريف واحد لا يتكرّر).

    name: سلسلة نوع الحدث كما تُصدَر فعلاً (الوسيط المُمرَّر لـ`_emit_domain_event`).
    version: إصدار شكل الحمولة (يبدأ من ١؛ يُرفع عند تغيير غير متوافق في الحقول).
    category: فئة منطقيّة (مثل field/season/activity/irrigation/alert/projection).
    description_ar: وصف عربيّ موجز لدلالة الحدث.
    payload_keys: أبرز حقول الحمولة (من قراءة نداء الإصدار الفعليّ؛ () إن لم نتأكّد).
    """

    name: str
    category: str
    description_ar: str
    version: int = 1
    payload_keys: tuple[str, ...] = field(default_factory=tuple)


# سجلّ الأحداث: فقط أنواع تحقّقنا أنّها تُصدَر فعلاً (نداءات _emit_domain_event في
# main.py/الراوترات، أو EventBus.emit/_emit بعضو EventType). مُجمَّع بالفئة. لا أحداث مُخترَعة.
_CATALOG: dict[str, DomainEvent] = {
    # ── الحقل (field): دورة حياة الحقل وتبدّل حالته القانونيّة الموحّدة ──────────
    "FIELD_CREATED": DomainEvent(
        name="FIELD_CREATED",
        category="field",
        description_ar="أُنشئ حقل جديد.",
        payload_keys=("name", "crop", "area_ha", "farm_id", "soil_type"),
    ),
    "FIELD_UPDATED": DomainEvent(
        name="FIELD_UPDATED",
        category="field",
        description_ar="حُدِّثت بيانات حقل قائم.",
    ),
    "FIELD_DELETED": DomainEvent(
        name="FIELD_DELETED",
        category="field",
        description_ar="حُذف حقل.",
    ),
    "FIELD_STATE_CHANGED": DomainEvent(
        name="FIELD_STATE_CHANGED",
        category="field",
        description_ar="تبدّلت الحالة القانونيّة الموحّدة للحقل (صلاحيّة/نمط تنفيذ).",
        payload_keys=("validity", "execution_mode", "trigger"),
    ),
    "FIELD_GEOMETRY_CHANGED": DomainEvent(
        name="FIELD_GEOMETRY_CHANGED",
        category="field",
        description_ar=(
            "تغيّرت حدود الحقل (مراجعة هندسة جديدة + إبطال كاش الراستر) عند الإنشاء أو "
            "تعديل الحدود (المُصدِر: routers/fields.py)."
        ),
        payload_keys=("geometry_revision", "reason"),
    ),
    "FIELD_GEOMETRY_REVERTED": DomainEvent(
        name="FIELD_GEOMETRY_REVERTED",
        category="field",
        description_ar="استُرجعت حدود الحقل لمراجعة سابقة (المُصدِر: routers/fields.py).",
        payload_keys=("geometry_revision", "reverted_from_revision"),
    ),
    "FIELD_IMAGERY_REFRESH_REQUESTED": DomainEvent(
        name="FIELD_IMAGERY_REFRESH_REQUESTED",
        category="field",
        description_ar="طُلب تحديث صور الأقمار للحقل (manual.refresh؛ المُصدِر: routers/fields.py).",
        payload_keys=("status", "queued"),
    ),
    "FIELD_IMAGERY_BACKFILL_REQUESTED": DomainEvent(
        name="FIELD_IMAGERY_BACKFILL_REQUESTED",
        category="field",
        description_ar="طُلبت سلسلة صور تاريخيّة للحقل (backfill؛ المُصدِر: routers/fields.py).",
        payload_keys=("preset", "months", "indices", "dry_run", "jobs_scheduled"),
    ),
    # ── الموسم (season): بدء/إغلاق/تحديث المواسم الزراعيّة ───────────────────────
    "SEASON_CREATED": DomainEvent(
        name="SEASON_CREATED",
        category="season",
        description_ar="أُنشئ موسم زراعيّ لحقل (نشط، أو مخطَّط لا يُغلق النشط).",
        payload_keys=("field_id", "crops", "status", "cultivar", "irrigation_type", "sowing_date"),
    ),
    "SEASON_CLOSED": DomainEvent(
        name="SEASON_CLOSED",
        category="season",
        description_ar="أُغلق موسم زراعيّ.",
    ),
    "SEASON_UPDATED": DomainEvent(
        name="SEASON_UPDATED",
        category="season",
        description_ar="حُدِّثت بيانات موسم قائم.",
    ),
    # ── النشاط/العمليّات (activity): حدث عامّ + أحداث operation.* المحدّدة ────────
    # أحداث operation.*.started (PLANTING/IRRIGATION/HARVEST_STARTED) محجوزة بلا مُصدِر
    # (قرار المالك 2026-11-14): لا يُنفَّذ «بدء» نشاط في أيّ مسار؛ المُخطَّط يُصدِر
    # ACTIVITY_RECORDED (field_aggregate.activity_event_for). مسجَّلة في
    # tests/test_event_catalog_completeness.py _RESERVED_NO_PRODUCER حتّى يوجد منتِج حقيقيّ.
    "ACTIVITY_RECORDED": DomainEvent(
        name="ACTIVITY_RECORDED",
        category="activity",
        description_ar="سُجّلت عمليّة عامّة أو مُخطَّطة/مُتخطّاة (المُنفَّذة: operation.*).",
        payload_keys=(
            "field_id",
            "season_id",
            "activity_type",
            "status",
            "scheduled_for",
            "performed_on",
        ),
    ),
    "PLANTING_COMPLETED": DomainEvent(
        name="PLANTING_COMPLETED",
        category="activity",
        description_ar="اكتملت عمليّة زراعة/بذر.",
    ),
    "IRRIGATION_COMPLETED": DomainEvent(
        name="IRRIGATION_COMPLETED",
        category="activity",
        description_ar="اكتملت عمليّة ريّ.",
    ),
    "FERTILIZER_APPLIED": DomainEvent(
        name="FERTILIZER_APPLIED",
        category="activity",
        description_ar="طُبِّق تسميد.",
    ),
    "PESTICIDE_APPLIED": DomainEvent(
        name="PESTICIDE_APPLIED",
        category="activity",
        description_ar="طُبِّق رشّ مبيد.",
    ),
    "HARVEST_COMPLETED": DomainEvent(
        name="HARVEST_COMPLETED",
        category="activity",
        description_ar="اكتملت عمليّة حصاد.",
    ),
    # ── المهامّ/المزارع/المرجعيّة (operations) — نقاط كتابة تفاعليّة ─────────────
    "TASK_UPDATED": DomainEvent(
        name="TASK_UPDATED",
        category="task",
        description_ar="حُدِّثت مهمّة.",
    ),
    "TASK_CREATED": DomainEvent(
        name="TASK_CREATED",
        category="task",
        description_ar=(
            "أُنشئت مهمّة من خطّة عمليّة الطقس (tasks/from-operation-plan؛ المُصدِر: routers/weather.py)."
        ),
        payload_keys=("field_id", "source", "operation"),
    ),
    "FARM_CREATED": DomainEvent(
        name="FARM_CREATED",
        category="farm",
        description_ar="أُنشئت مزرعة جديدة.",
    ),
    "INVENTORY_ITEM_CREATED": DomainEvent(
        name="INVENTORY_ITEM_CREATED",
        category="inventory",
        description_ar="أُنشئ صنف مخزون.",
    ),
    "INVENTORY_BATCH_ADDED": DomainEvent(
        name="INVENTORY_BATCH_ADDED",
        category="inventory",
        description_ar="أُضيفت دفعة مخزون.",
    ),
    "EQUIPMENT_CREATED": DomainEvent(
        name="EQUIPMENT_CREATED",
        category="equipment",
        description_ar="سُجِّلت معدّة.",
    ),
    "MAINTENANCE_LOGGED": DomainEvent(
        name="MAINTENANCE_LOGGED",
        category="equipment",
        description_ar="سُجّلت صيانة معدّة.",
    ),
    "MASTER_DATA_CREATED": DomainEvent(
        name="MASTER_DATA_CREATED",
        category="master_data",
        description_ar="أُنشئ سجلّ بيانات مرجعيّة.",
    ),
    "CROP_ROTATION_ADDED": DomainEvent(
        name="CROP_ROTATION_ADDED",
        category="crop_rotation",
        description_ar="أُضيفت دورة زراعيّة.",
    ),
    # ── التربة (soil): عيّنات ونتائج مختبر ──────────────────────────────────────
    "SOIL_SAMPLE_RECORDED": DomainEvent(
        name="SOIL_SAMPLE_RECORDED",
        category="soil",
        description_ar="سُجّلت عيّنة تربة.",
    ),
    "SOIL_LAB_RESULT_PUBLISHED": DomainEvent(
        name="SOIL_LAB_RESULT_PUBLISHED",
        category="soil",
        description_ar="نُشرت نتيجة مختبر تربة.",
    ),
    # ── التنبيهات (alert): تنبيهات زراعيّة تفاعليّة عبر الأحداث ──────────────────
    "ALERT_CREATED": DomainEvent(
        name="ALERT_CREATED",
        category="alert",
        description_ar="أُنشئ تنبيه زراعيّ.",
        payload_keys=("severity", "alert_type", "field_id"),
    ),
    "ALERT_ACKNOWLEDGED": DomainEvent(
        name="ALERT_ACKNOWLEDGED",
        category="alert",
        description_ar="أُقِرّ (acknowledged) تنبيه.",
    ),
    "NOTIFICATION_DELIVERED": DomainEvent(
        name="NOTIFICATION_DELIVERED",
        category="notification",
        description_ar="أُدِيمت/حُدِّثت حالة تسليم إشعار عبر قناة (الوسيط: notification.delivered).",
        payload_keys=("alert_key", "channel", "status"),
    ),
    # ── الريّ (irrigation): جدولة + دورة حياة الصمّامات ─────────────────────────
    "IRRIGATION_SCHEDULE_CREATED": DomainEvent(
        name="IRRIGATION_SCHEDULE_CREATED",
        category="irrigation",
        description_ar="أُنشئ جدول ريّ.",
    ),
    # ملاحظة: حدثا الصمّامات يُسجَّلان باسم عضو EventType (بأحرف كبيرة) تماشياً مع
    # سائر مدخلات السجلّ؛ قيمة الوسيط NATS المنقّطة محفوظة في الوصف للمرجعيّة.
    "IRRIGATION_VALVE_REGISTERED": DomainEvent(
        name="IRRIGATION_VALVE_REGISTERED",
        category="irrigation",
        description_ar="سُجِّل صمّام ريّ (الوسيط: irrigation.valve.registered).",
        payload_keys=("field_id", "valve_type"),
    ),
    "IRRIGATION_VALVE_STATE_CHANGED": DomainEvent(
        name="IRRIGATION_VALVE_STATE_CHANGED",
        category="irrigation",
        description_ar="تبدّلت حالة صمّام ريّ (الوسيط: irrigation.valve.state_changed).",
        payload_keys=("status",),
    ),
    # IRR-F01 Gate B: نيّة إرسال الحجز عبر outbox (المُصدِر:
    # irrigation_execution_request_port.py، يُمرِّر قيمة EventType المنقّطة لا الاسم).
    "IRRIGATION_RESERVATION_DISPATCH_REQUESTED": DomainEvent(
        name="IRRIGATION_RESERVATION_DISPATCH_REQUESTED",
        category="irrigation",
        description_ar=(
            "طُلب إرسال حجز ريّ للتنفيذ عبر outbox — نيّة لا تنفيذ "
            "(الوسيط: irrigation.reservation.dispatch_requested)."
        ),
        payload_keys=(
            "evaluation_id",
            "reservation_ids",
            "execution_ref_type",
            "execution_ref_id",
            "state",
            "correlation_id",
            "causation_id",
        ),
    ),
    "IRRIGATION_RESERVATION_DISPATCH_FAILED": DomainEvent(
        name="IRRIGATION_RESERVATION_DISPATCH_FAILED",
        category="irrigation",
        description_ar=(
            "فشل إرسال حجز ريّ للتنفيذ (الوسيط: irrigation.reservation.dispatch_failed)."
        ),
        payload_keys=("execution_request_ref", "reason", "correlation_id", "causation_id"),
    ),
    # ── توزيع القرار (dispatch): تدقيق نقاط كتابة decision_dispatch (H3) ──────────
    "DISPATCH_DECISION_RECORDED": DomainEvent(
        name="DISPATCH_DECISION_RECORDED",
        category="dispatch",
        description_ar="سُجِّل قرار توزيع (الوسيط: dispatch.decision.recorded).",
        payload_keys=("state", "action_type", "field_id", "exec_status"),
    ),
    "DISPATCH_EXECUTION_RECORDED": DomainEvent(
        name="DISPATCH_EXECUTION_RECORDED",
        category="dispatch",
        description_ar="سُجِّلت نتيجة تنفيذ قرار (الوسيط: dispatch.execution.recorded).",
        payload_keys=("outcome", "decision_id", "field_id"),
    ),
    # ── سلسلة النَّسَب المُدامة (lineage): إدامة القرار ونتيجته (P0-1/P0-3) ──────────
    "DECISION_RECORDED": DomainEvent(
        name="DECISION_RECORDED",
        category="lineage",
        description_ar="أُدِيم قرار زراعيّ (رأس السلسلة؛ الوسيط: decision.recorded).",
        payload_keys=("decision_type", "field_id", "region", "confidence"),
    ),
    "OUTCOME_MEASURED": DomainEvent(
        name="OUTCOME_MEASURED",
        category="lineage",
        description_ar="أُدِيمت نتيجة قرار ميدانيّة مربوطة بـdecision_id (الوسيط: outcome.measured).",
        payload_keys=("decision_id", "field_id", "success"),
    ),
    "LINEAGE_LINKED": DomainEvent(
        name="LINEAGE_LINKED",
        category="lineage",
        description_ar="رُبِط مرجع قائم بمعرّف نَسَب عالميّ موحّد lin_ (الوسيط: lineage.linked).",
        payload_keys=("lineage_id", "ref_type", "ref_id"),
    ),
    # ── المعايرة الإقليميّة المُدارة (calibration): إدامة قيم مُتحقَّقة DB-backed ──────
    "CALIBRATION_OVERRIDE_SET": DomainEvent(
        name="CALIBRATION_OVERRIDE_SET",
        category="calibration",
        description_ar="أُدِيمت قيم معايرة إقليميّة مُتحقَّقة لمنطقة (الوسيط: calibration.override.set).",
        payload_keys=("region", "fields"),
    ),
    "CALIBRATION_AUDIT_RECORDED": DomainEvent(
        name="CALIBRATION_AUDIT_RECORDED",
        category="calibration",
        description_ar="دُوِّن قيد تدقيق append-only لتغيير معايرة منطقة (الوسيط: calibration.audit.recorded).",
        payload_keys=("region", "action"),
    ),
    # ── المزامنة offline: دمج آليّ غير متقاطع (Auto-merge L3) ────────────────────
    "OFFLINE_MERGE_AUTO": DomainEvent(
        name="OFFLINE_MERGE_AUTO",
        category="offline",
        description_ar="دُمِجت تعديلات offline غير متقاطعة آليّاً (الوسيط: offline.merge.auto).",
        payload_keys=("merged_fields", "server_version_before"),
    ),
    # ── التوصيات وأوامر العمل (recommendation / work_order) ─────────────────────
    "RECOMMENDATION_CREATED": DomainEvent(
        name="RECOMMENDATION_CREATED",
        category="recommendation",
        description_ar=(
            "خُزِّنت توصية. مُصدِران: routers/recommendations.py (delivered, field_id, crop) "
            "وrouters/weather.py لخطّة عمليّة الطقس (field_id, source)."
        ),
        payload_keys=("field_id", "delivered", "crop", "source"),
    ),
    "WORK_ORDER_CREATED": DomainEvent(
        name="WORK_ORDER_CREATED",
        category="work_order",
        description_ar=(
            "ثُبِّت أمر عمل مُشتقّ من توصية بعد إدراج صفّه (المُصدِر: routers/agro_intelligence.py)."
        ),
        payload_keys=("field_id", "wo_type", "status", "recommendation_id"),
    ),
    # ── معايرة الإنتاجيّة (trueup) ───────────────────────────────────────────────
    "TRUEUP_APPLIED": DomainEvent(
        name="TRUEUP_APPLIED",
        category="trueup",
        description_ar=(
            "طُبِّقت معايرة إنتاجيّة TrueUp (المُصدِر: TrueUpEngine.apply في trueup.py؛ "
            "المثيل الموصَّل في main.py بلا pool، فهذا المسار غير مُفعَّل على مسار الطلب حاليّاً)."
        ),
        payload_keys=(
            "operation_id",
            "k_old",
            "k_new",
            "measured_yield_kg_ha",
            "adjusted_yield_kg_ha",
            "error_pct",
            "moisture_corrected",
        ),
    ),
    # ── الذكاء الاصطناعيّ (ai): اقتراح دليليّ لا قرار ─────────────────────────────
    "AI_SUGGESTION": DomainEvent(
        name="AI_SUGGESTION",
        category="ai",
        description_ar=(
            "سُجِّلت نصيحة مستشار الذكاء كدليل فقط لا قرار "
            "(المُصدِر: routers/internal_service.py، /internal/events/ai-advice)."
        ),
        payload_keys=(
            "field_id",
            "question",
            "evidence_ids",
            "confidence",
            "selected_imagery_date",
            "endpoint_mode",
            "decision_authority",
            "runtime",
            "advisory_validation",
        ),
    ),
    # ── تتبّع سلسلة الإمداد (traceability): الحصاد والحيازة وخرائط الإنتاجيّة ──────
    "HARVEST_LOT_CREATED": DomainEvent(
        name="HARVEST_LOT_CREATED",
        category="traceability",
        description_ar="أُنشئت دفعة حصاد (المُصدِر: routers/harvest_traceability.py).",
        payload_keys=("field_id", "season_id", "quantity_kg", "phi_check"),
    ),
    "CUSTODY_EVENT_RECORDED": DomainEvent(
        name="CUSTODY_EVENT_RECORDED",
        category="traceability",
        description_ar="سُجِّل حدث حيازة لدفعة حصاد (المُصدِر: routers/harvest_traceability.py).",
        payload_keys=("event_type", "custody_event_id", "new_status"),
    ),
    "YIELD_MAP_INGESTED": DomainEvent(
        name="YIELD_MAP_INGESTED",
        category="traceability",
        description_ar="استُورِدت خريطة إنتاجيّة لحقل (المُصدِر: routers/yield_map_ingestion.py).",
        payload_keys=("field_id", "season_id", "source_sha256", "record_count"),
    ),
}


def list_events() -> list[dict]:
    """يُرجِع كلّ الأحداث المسجَّلة (مرتّبة بالاسم) كقواميس — للعرض/الحوكمة."""
    return [get_event(name) for name in sorted(_CATALOG)]  # type: ignore[misc]


def get_event(name: str) -> dict | None:
    """يُرجِع وصف حدث باسمه كقاموس، أو None إن لم يكن مسجَّلاً (لا اختراع)."""
    ev = _CATALOG.get(name)
    if ev is None:
        return None
    return {
        "name": ev.name,
        "version": ev.version,
        "category": ev.category,
        "description_ar": ev.description_ar,
        "payload_keys": list(ev.payload_keys),
    }


def known_event_names() -> list[str]:
    """يُرجِع أسماء كلّ أنواع الأحداث المسجَّلة (مرتّبة)."""
    return sorted(_CATALOG)


def is_registered(name: str) -> bool:
    """هل اسم نوع الحدث مسجَّل في السجلّ؟ (أساس حارس الحوكمة المستقبليّ)."""
    return name in _CATALOG
