"""مصفوفة قدرات وكيل الذكاء (V55 — Agricultural Agent Harness).

توسيعٌ لحوكمة V52: بدل مستوى مشاركة البيانات وحده، يحمل كلّ مستأجِر **قائمة قدرات
مسموحة** (`can_*`) تحكم أيّ أدوات يجوز للنموذج استخدامها. كلّ أداة في
``shared/ai/tool_registry`` تُعلن قدرةً مطلوبة؛ فبلا القدرة لا تُستدعى الأداة.

هذا الملفّ **المصدر القانونيّ الواحد** للقدرات؛ يفرض الحارس
``tests_v9/test_ai_tool_registry_v55.py`` تطابق سجلّ الأدوات وجدول المستأجِر معه.
المفاتيح السرّيّة/التنفيذ ليست هنا — هذا عقد أذونات صرف.
"""

from __future__ import annotations

from collections.abc import Iterable

# ──────────────────────────────────────────────────────────────────────────
# القدرات القانونيّة — ما الذي يُسمَح للوكيل بفعله (قراءةً أو تعديلاً) لكلّ مستأجِر.
# ──────────────────────────────────────────────────────────────────────────
CAN_READ_FIELD_DATA = "can_read_field_data"
CAN_READ_HISTORICAL_IMAGERY = "can_read_historical_imagery"
CAN_USE_EXTERNAL_LLM = "can_use_external_llm"
CAN_CREATE_TASKS = "can_create_tasks"
CAN_MANAGE_FIELD_BOUNDARIES = "can_manage_field_boundaries"
CAN_MANAGE_PRODUCTIVITY_ZONES = "can_manage_productivity_zones"
CAN_MANAGE_SOIL_SAMPLING = "can_manage_soil_sampling"
CAN_GENERATE_PRESCRIPTIONS = "can_generate_prescriptions"
CAN_SEND_RECOMMENDATIONS = "can_send_recommendations"
CAN_TRIGGER_BACKFILL = "can_trigger_backfill"
CAN_EXPORT_ENTERPRISE_DATA = "can_export_enterprise_data"

CAPABILITIES: tuple[str, ...] = (
    CAN_READ_FIELD_DATA,
    CAN_READ_HISTORICAL_IMAGERY,
    CAN_USE_EXTERNAL_LLM,
    CAN_CREATE_TASKS,
    CAN_MANAGE_FIELD_BOUNDARIES,
    CAN_MANAGE_PRODUCTIVITY_ZONES,
    CAN_MANAGE_SOIL_SAMPLING,
    CAN_GENERATE_PRESCRIPTIONS,
    CAN_SEND_RECOMMENDATIONS,
    CAN_TRIGGER_BACKFILL,
    CAN_EXPORT_ENTERPRISE_DATA,
)

# الافتراضيّ المتحفّظ (fail-closed): يُمنَح المستأجِر القراءةَ فقط حتى يُفعَّل غيرها
# صراحةً. لا توليد خارجيّ ولا أفعال مُعدِّلة بلا منح صريح — يوازي `local_only` في V52.
DEFAULT_CAPABILITIES: tuple[str, ...] = (
    CAN_READ_FIELD_DATA,
    CAN_READ_HISTORICAL_IMAGERY,
)

# القدرات التي تفتح أفعالاً مُعدِّلة/عالية الأثر (تُدقَّق وتحتاج منحاً صريحاً + غالباً
# موافقة بشريّة على مستوى الأداة — انظر ``tool_registry``).
MUTATING_CAPABILITIES: frozenset[str] = frozenset(
    {
        CAN_CREATE_TASKS,
        CAN_MANAGE_FIELD_BOUNDARIES,
        CAN_MANAGE_PRODUCTIVITY_ZONES,
        CAN_MANAGE_SOIL_SAMPLING,
        CAN_GENERATE_PRESCRIPTIONS,
        CAN_SEND_RECOMMENDATIONS,
        CAN_TRIGGER_BACKFILL,
        CAN_EXPORT_ENTERPRISE_DATA,
    }
)


def normalize_capabilities(caps: Iterable[str] | None) -> tuple[str, ...]:
    """يُطبِّع قائمة القدرات: يُبقي المعروفة فقط بترتيب ``CAPABILITIES`` القانونيّ،
    ويُسقط المجهولة (لا يثق بقيمة غير مُعرَّفة). ``None`` ⇒ الافتراضيّ المتحفّظ."""
    if caps is None:
        return DEFAULT_CAPABILITIES
    granted = {str(c).strip().lower() for c in caps}
    return tuple(c for c in CAPABILITIES if c in granted)


def has_capability(granted: Iterable[str] | None, capability: str) -> bool:
    """هل القدرة ممنوحة؟ يُطبِّع أوّلاً (قيمة مجهولة لا تمنح شيئاً)."""
    return capability in set(normalize_capabilities(granted))
