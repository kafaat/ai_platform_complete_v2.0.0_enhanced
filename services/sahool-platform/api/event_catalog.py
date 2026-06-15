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

ملاحظة عن التوصيل (wiring): التأكيد على أنّ كلّ اسم مُمرَّر لـ`_emit_domain_event`
موجود في هذا السجلّ هو حارس CI قيّم (follow-up)، لم يُنفَّذ هنا. الأسماء المسرودة
أدناه مأخوذة حرفيّاً ممّا يُصدَر فعلاً في `api/main.py` (لا اختراع لأحداث).
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


# سجلّ الأحداث: مبذور فقط بأنواع تحقّقنا أنّها تُصدَر فعلاً في api/main.py
# (نداءات _emit_domain_event). مُجمَّع بالفئة. لا أحداث مُخترَعة.
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
    # ── الموسم (season): بدء/إغلاق/تحديث المواسم الزراعيّة ───────────────────────
    "SEASON_CREATED": DomainEvent(
        name="SEASON_CREATED",
        category="season",
        description_ar="بُدئ موسم زراعيّ لحقل.",
        payload_keys=("field_id", "crops", "cultivar", "irrigation_type", "sowing_date"),
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
    "ACTIVITY_RECORDED": DomainEvent(
        name="ACTIVITY_RECORDED",
        category="activity",
        description_ar="سُجّلت عمليّة حقليّة عامّة (يكمّلها أحداث operation.* المحدّدة).",
    ),
    "PLANTING_STARTED": DomainEvent(
        name="PLANTING_STARTED",
        category="activity",
        description_ar="بدأت عمليّة زراعة/بذر.",
    ),
    "PLANTING_COMPLETED": DomainEvent(
        name="PLANTING_COMPLETED",
        category="activity",
        description_ar="اكتملت عمليّة زراعة/بذر.",
    ),
    "IRRIGATION_STARTED": DomainEvent(
        name="IRRIGATION_STARTED",
        category="activity",
        description_ar="بدأت عمليّة ريّ.",
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
    "HARVEST_STARTED": DomainEvent(
        name="HARVEST_STARTED",
        category="activity",
        description_ar="بدأت عمليّة حصاد.",
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
    # ── الريّ (irrigation): جدولة + دورة حياة الصمّامات ─────────────────────────
    "IRRIGATION_SCHEDULE_CREATED": DomainEvent(
        name="IRRIGATION_SCHEDULE_CREATED",
        category="irrigation",
        description_ar="أُنشئ جدول ريّ.",
    ),
    # ملاحظة: الاسمان التاليان يُمرَّران لـ_emit_domain_event كسلسلتين منقّطتين
    # حرفيّتين (لا كاسم عضو EventType بأحرف كبيرة) — نسجّلهما بالشكل المُصدَر فعلاً.
    "irrigation.valve.registered": DomainEvent(
        name="irrigation.valve.registered",
        category="irrigation",
        description_ar="سُجِّل صمّام ريّ.",
        payload_keys=("field_id", "valve_type"),
    ),
    "irrigation.valve.state_changed": DomainEvent(
        name="irrigation.valve.state_changed",
        category="irrigation",
        description_ar="تبدّلت حالة صمّام ريّ.",
        payload_keys=("status",),
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
