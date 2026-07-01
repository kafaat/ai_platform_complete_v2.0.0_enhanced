"""سجلّ أدوات وكيل الذكاء الزراعيّ (V55 — Agricultural Agent Harness).

الفلسفة (قرار المستخدم): **النموذج يقرّر؛ الـHarness يوفّر الأدوات والسياق والأذونات
والتدقيق.** ليس شجرة if/else ولا workflow جامداً. هذا السجلّ هو الكتلوج التعريفيّ
للأدوات التي يجوز للنموذج اختيارها؛ كلّ أداة تُعلن:

- ``risk`` (low/medium/high) — يحدّد الحوكمة (العالية تحتاج موافقة بشريّة).
- ``capability`` — القدرة المطلوبة (من ``shared/ai/capabilities``)؛ بلا المنح لا تُستدعى.
- ``mutating`` — أتُعدّل حالةً أم قراءة فقط.
- ``requires_approval`` — أتحتاج موافقة بشريّة صريحة قبل التنفيذ.
- ``params`` — مخطّط وسائط بسيط (اسم ⇒ نوع) للتحقّق/العرض.

**عقد صرف بلا تنفيذ** (المرحلة ١): التنفيذ الفعليّ ووصل النقاط يأتيان في مراحل تالية.
يفرض الحارس ``tests_v9/test_ai_tool_registry_v55.py`` سلامة السجلّ (كلّ أداة لها قدرة
قانونيّة + خطورة، العالية تحتاج موافقة، المُعدِّلة ليست low، الأسماء فريدة).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.ai.capabilities import (
    CAN_CREATE_TASKS,
    CAN_EXPORT_ENTERPRISE_DATA,
    CAN_GENERATE_PRESCRIPTIONS,
    CAN_MANAGE_FIELD_BOUNDARIES,
    CAN_MANAGE_PRODUCTIVITY_ZONES,
    CAN_MANAGE_SOIL_SAMPLING,
    CAN_READ_FIELD_DATA,
    CAN_READ_HISTORICAL_IMAGERY,
    CAN_SEND_RECOMMENDATIONS,
    CAN_TRIGGER_BACKFILL,
    CAPABILITIES,
)

# مستويات الخطورة — تحكم بوّابة الموافقة (انظر رأس الملفّ).
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_LEVELS: tuple[str, ...] = (RISK_LOW, RISK_MEDIUM, RISK_HIGH)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description_ar: str
    risk: str
    capability: str
    mutating: bool
    requires_approval: bool
    params: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # ثوابت السلامة تُفرَض وقت البناء (بالإضافة إلى الحارس الساكن):
        if self.risk not in RISK_LEVELS:
            raise ValueError(f"خطورة غير قانونيّة للأداة {self.name}: {self.risk}")
        if self.capability not in CAPABILITIES:
            raise ValueError(f"قدرة غير قانونيّة للأداة {self.name}: {self.capability}")
        if self.risk == RISK_HIGH and not self.requires_approval:
            raise ValueError(f"أداة عالية الخطورة بلا موافقة بشريّة: {self.name}")
        if self.mutating and self.risk == RISK_LOW:
            raise ValueError(f"أداة مُعدِّلة لا يجوز أن تكون low: {self.name}")
        if not self.mutating and self.requires_approval:
            raise ValueError(f"أداة قراءة لا تحتاج موافقة: {self.name}")


# ──────────────────────────────────────────────────────────────────────────
# الكتلوج — أدوات القراءة (منخفضة الخطر) ثمّ التعديل (متوسّطة) ثمّ عالية الأثر.
# ──────────────────────────────────────────────────────────────────────────
TOOLS: tuple[ToolSpec, ...] = (
    # ── قراءة (low) — لا تُعدّل شيئاً، الافتراضيّ مسموح ──
    ToolSpec(
        "get_field_state",
        "يقرأ الحالة القانونيّة الحاليّة للحقل (محصول/مرحلة/مؤشّرات/ريّ).",
        RISK_LOW,
        CAN_READ_FIELD_DATA,
        False,
        False,
        {"field_id": "str"},
    ),
    ToolSpec(
        "get_truecolor_scene",
        "يجلب مشهد TrueColor الخام للحقل بتاريخ (أو الأحدث) مع جاهزيّته.",
        RISK_LOW,
        CAN_READ_HISTORICAL_IMAGERY,
        False,
        False,
        {"field_id": "str", "date": "str?"},
    ),
    ToolSpec(
        "get_index_timeline",
        "سلسلة زمنيّة لمؤشّر (ndvi/ndmi…) عبر مدّة أيّام.",
        RISK_LOW,
        CAN_READ_HISTORICAL_IMAGERY,
        False,
        False,
        {"field_id": "str", "index": "str", "days": "int"},
    ),
    ToolSpec(
        "get_weather_history",
        "طقس تاريخيّ للحقل (حتى 730 يوماً): حرارة/مطر/ET0.",
        RISK_LOW,
        CAN_READ_FIELD_DATA,
        False,
        False,
        {"field_id": "str", "days": "int"},
    ),
    ToolSpec(
        "get_operation_windows",
        "نوافذ الرشّ/الريّ الملائمة (رياح/مطر/رطوبة).",
        RISK_LOW,
        CAN_READ_FIELD_DATA,
        False,
        False,
        {"field_id": "str"},
    ),
    ToolSpec(
        "get_alerts",
        "تنبيهات الحقل النشطة (إجهاد/مرض/صقيع…).",
        RISK_LOW,
        CAN_READ_FIELD_DATA,
        False,
        False,
        {"field_id": "str"},
    ),
    ToolSpec(
        "get_drawings_and_zones",
        "الرسومات والمناطق الإنتاجيّة والمحاور المرسومة للحقل.",
        RISK_LOW,
        CAN_READ_FIELD_DATA,
        False,
        False,
        {"field_id": "str"},
    ),
    ToolSpec(
        "open_map_layer",
        "يفتح طبقة خريطة (truecolor/مؤشّر) بتاريخ للعرض — فعل واجهة لا يُعدّل بيانات.",
        RISK_LOW,
        CAN_READ_FIELD_DATA,
        False,
        False,
        {"field_id": "str", "layer": "str", "date": "str?"},
    ),
    ToolSpec(
        "detect_field_boundaries",
        "يقترح حدود الحقل من bbox/صورة TrueColor أو مؤشر، ولا يحفظها دون تأكيد المستخدم.",
        RISK_LOW,
        CAN_READ_HISTORICAL_IMAGERY,
        False,
        False,
        {"bbox": "bbox", "source": "str?", "date": "str?", "crop_hint": "str?"},
    ),
    ToolSpec(
        "generate_productivity_zones",
        "يقترح مناطق إنتاجية داخل حدود الحقل من المؤشرات التاريخية/التربة/الطقس، ولا يحفظها دون تأكيد المستخدم.",
        RISK_LOW,
        CAN_READ_HISTORICAL_IMAGERY,
        False,
        False,
        {
            "field_id": "str?",
            "boundary": "geojson?",
            "bbox": "bbox?",
            "zone_count": "int?",
            "basis": "str?",
        },
    ),
    # ── تعديل (medium) — تحتاج قدرة صريحة؛ مسوّدات لا نهائيّات ──
    ToolSpec(
        "plan_soil_sampling",
        "يقترح خطة أخذ عينات تربة ممثلة لكل منطقة إنتاجية، ولا ينشئ مهاماً أو يحفظ خطة دون تأكيد المستخدم.",
        RISK_LOW,
        CAN_READ_HISTORICAL_IMAGERY,
        False,
        False,
        {
            "field_id": "str?",
            "zones": "array?",
            "boundary": "geojson?",
            "bbox": "bbox?",
            "lab_panel": "str?",
            "samples_per_zone": "int?",
        },
    ),
    ToolSpec(
        "generate_vra_prescription",
        "يقترح وصفة معدّل متغيّر VRA من مناطق الإنتاجية وخطة/نتائج التربة، ولا يحفظ أو يصدر خريطة آلة دون موافقة بشرية.",
        RISK_LOW,
        CAN_READ_HISTORICAL_IMAGERY,
        False,
        False,
        {
            "field_id": "str?",
            "zones": "array?",
            "soil_sampling_plan": "object?",
            "lab_results": "array?",
            "crop": "str?",
            "target_yield": "float?",
            "product_type": "str?",
            "base_rate": "float?",
            "unit": "str?",
            "allow_estimated": "bool?",
        },
    ),
    ToolSpec(
        "create_scouting_task",
        "ينشئ مهمّة كشف ميدانيّ لمنطقة من الحقل.",
        RISK_MEDIUM,
        CAN_CREATE_TASKS,
        True,
        False,
        {"field_id": "str", "zone": "str"},
    ),
    ToolSpec(
        "request_imagery_backfill",
        "يشغّل تجهيز صور تاريخيّة (أشهر) للحقل.",
        RISK_MEDIUM,
        CAN_TRIGGER_BACKFILL,
        True,
        False,
        {"field_id": "str", "months": "int"},
    ),
    ToolSpec(
        "draft_recommendation",
        "يُنشئ **مسوّدة** توصية (لا تُرسَل) قابلة للمراجعة البشريّة.",
        RISK_MEDIUM,
        CAN_SEND_RECOMMENDATIONS,
        True,
        False,
        {"field_id": "str"},
    ),
    ToolSpec(
        "save_detected_boundary",
        "يحفظ حدوداً مقترحة كحدود حقل رسمية بعد موافقة/تأكيد المستخدم.",
        RISK_HIGH,
        CAN_MANAGE_FIELD_BOUNDARIES,
        True,
        True,
        {"field_id": "str", "proposal_id": "str"},
    ),
    ToolSpec(
        "save_productivity_zones",
        "يحفظ مناطق إنتاجية مقترحة بعد موافقة/تأكيد المستخدم، لتصبح أساساً لأخذ عينات التربة والوصفات المتغيرة.",
        RISK_HIGH,
        CAN_MANAGE_PRODUCTIVITY_ZONES,
        True,
        True,
        {"field_id": "str", "proposal_id": "str"},
    ),
    # ── عالية الأثر (high) — تتطلّب موافقة بشريّة صريحة ──
    ToolSpec(
        "save_soil_sampling_plan",
        "يحفظ خطة عينات التربة المقترحة أو يحولها إلى مهام ميدانية بعد موافقة/تأكيد المستخدم.",
        RISK_HIGH,
        CAN_MANAGE_SOIL_SAMPLING,
        True,
        True,
        {"field_id": "str", "plan_id": "str"},
    ),
    ToolSpec(
        "send_recommendation",
        "يُرسِل توصية نهائيّة للمزارع (فعل نهائيّ).",
        RISK_HIGH,
        CAN_SEND_RECOMMENDATIONS,
        True,
        True,
        {"field_id": "str", "recommendation_id": "str"},
    ),
    ToolSpec(
        "create_prescription_map",
        "يحفظ/ينشئ خريطة وصفة معدّل-متغيّر VRA رسمية أو يجهّزها للتصدير بعد موافقة بشرية ومراجعة مهندس زراعي.",
        RISK_HIGH,
        CAN_GENERATE_PRESCRIPTIONS,
        True,
        True,
        {"field_id": "str", "prescription_id": "str", "product_type": "str"},
    ),
    ToolSpec(
        "schedule_irrigation",
        "يجدول ريّاً/رشّاً (أمر تشغيليّ مؤثّر).",
        RISK_HIGH,
        CAN_SEND_RECOMMENDATIONS,
        True,
        True,
        {"field_id": "str", "plan": "str"},
    ),
    ToolSpec(
        "export_enterprise_data",
        "يُصدّر بيانات مؤسّسيّة خارج حدّ المستأجِر (حسّاس).",
        RISK_HIGH,
        CAN_EXPORT_ENTERPRISE_DATA,
        True,
        True,
        {"scope": "str"},
    ),
)

_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOLS}


def get_tool(name: str) -> ToolSpec | None:
    return _BY_NAME.get(name)


def tool_names() -> tuple[str, ...]:
    return tuple(_BY_NAME)


def tools_by_risk(risk: str) -> tuple[ToolSpec, ...]:
    return tuple(t for t in TOOLS if t.risk == risk)


def requires_human_approval(name: str) -> bool:
    """هل تتطلّب الأداة موافقة بشريّة صريحة؟ (المجهولة ⇒ True، fail-closed)."""
    tool = get_tool(name)
    return True if tool is None else tool.requires_approval
