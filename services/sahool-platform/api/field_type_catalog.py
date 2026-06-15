"""services/sahool-platform/api/field_type_catalog.py — كتالوج أنواع الحقول (Field Type Catalog).

المشكلة: يميل الكود إلى تفريع السلوك بشروط حرفيّة من نوع `if field_type == "farm"`
منثورة عبر الوحدات — فلا مصدر واحد يصف ما هي أنواع الحقول، ولا حوكمة لها، وإضافة نوع
جديد تعني تعديل كود في أماكن متفرّقة بدل إضافة سطر بيانات.

ما يفعله هذا الملف: يجمع أنواع الحقول في **مصدر واحد للحقيقة** (single source of truth)
بصفتها **بيانات وصفيّة** (metadata): كلّ نوع يُعرَّف مرّة واحدة بمعرّفه واسمه العربيّ
ونوع هندسته (geometry) والأنشطة المسموح بها عليه. هكذا تصبح إضافة نوع جديد **إدخال
بيانات** في `_CATALOG` لا تعديلاً منطقيّاً.

أمانة عن الأساس (grounding): فحصُ المنصّة الحاليّة (جدول `field_state` في
`storage/lite_store.py`) يُظهر أنّه **لا يوجد عمود صريح `field_type`** اليوم؛ الحقول
تُمثَّل مكانيّاً كمضلّعات (boundary GeoJSON Polygon في `core/spatial/field_bundle.py`).
لذلك يُعرّف هذا الكتالوج **المفردات** (vocabulary) لخاصّيّة `field_type` مستقبليّة
(عمل لاحق / follow-up: إضافة العمود وربط السلوك به) بدل افتراض وجودها. الأنواع المبذورة
محايدة ومدافَع عنها (open_field / orchard / greenhouse / pasture) لا مُخترعة لحالة بعينها.

عن الأنشطة المسموحة (`allowed_activities`): تستخدم **معرّفات أنواع الأنشطة الحقيقيّة**
كما هي في قيد قاعدة البيانات `CHECK (activity_type IN ...)` ضمن `activity_log`
في `storage/lite_store.py` وفي `ActivityType` في `core/activity_log.py`، أي:
    irrigation, fertilization, pesticide, seeding, harvest,
    pruning, weeding, observation, other
ملاحظة على المصطلحات: ما يسمّيه بعضهم "planting" هو هنا `seeding`، و"spraying" هو
`pesticide`، و"scouting" هو `observation` — التزمنا بالمعرّفات الفعليّة لا المرادفات.

هذا الملفّ **نقيّ** تماماً: لا قاعدة بيانات ولا شبكة — بيانات وصفيّة (metadata) فقط.
لا نخترع قواعد زراعيّة (agronomy) أبعد من الواضح؛ والتفصيل موثّق عند كلّ نوع.
"""

from __future__ import annotations

from dataclasses import dataclass

# مجموعة هندسات الحقل المسموح بها (geometry kinds) — مرجع داخليّ للتحقّق.
GEOMETRY_KINDS: frozenset[str] = frozenset({"polygon", "point", "multipolygon"})

# معرّفات أنواع الأنشطة الحقيقيّة — مطابقة لقيد قاعدة البيانات وللـ ActivityType.
# مذكورة هنا توثيقاً فقط؛ المصدر الملزِم يبقى activity_log / lite_store.
_REAL_ACTIVITY_TYPES: frozenset[str] = frozenset(
    {
        "irrigation",
        "fertilization",
        "pesticide",
        "seeding",
        "harvest",
        "pruning",
        "weeding",
        "observation",
        "other",
    }
)


@dataclass(frozen=True)
class FieldType:
    """وصف نوع حقل واحد (تعريف واحد لا يتكرّر) كبيانات وصفيّة.

    id: معرّف ثابت بالإنجليزيّة (مثل "open_field") — مفتاح مستقرّ للتخزين والكود.
    name_ar: الاسم العربيّ المعروض للمستخدم.
    geometry_kind: نوع الهندسة المتوقّع ("polygon" | "point" | "multipolygon").
    allowed_activities: أنواع الأنشطة المسموح بها — بمعرّفات الأنشطة الحقيقيّة فقط.
    description_ar: وصف عربيّ موجز يشرح اختيارات النوع (اختياريّ).
    """

    id: str
    name_ar: str
    geometry_kind: str
    allowed_activities: tuple[str, ...]
    description_ar: str = ""


# ── الكتالوج: أنواع محايدة مدافَع عنها، الأنشطة بمعرّفات الأنشطة الحقيقيّة ──────────
_CATALOG: dict[str, FieldType] = {
    # حقل مكشوف: محاصيل حقليّة عامّة — تُسمح كلّ الأنشطة المعتادة لدورة الموسم.
    "open_field": FieldType(
        id="open_field",
        name_ar="حقل مكشوف",
        geometry_kind="polygon",
        allowed_activities=(
            "seeding",
            "fertilization",
            "irrigation",
            "pesticide",
            "weeding",
            "harvest",
            "observation",
        ),
        description_ar=("حقل محاصيل حقليّة مكشوف؛ يدعم دورة الموسم كاملة من البذر إلى الحصاد."),
    ),
    # بستان: محاصيل معمّرة (أشجار) — نستبعد البذر (seeding) لأنّ الزراعة لمرّة واحدة
    # عند الإنشاء لا عمليّة موسميّة متكرّرة؛ ونُدرج التقليم (pruning) كنشاط رئيسيّ.
    # التبرير: في المعمّرات لا يُعاد البذر كلّ موسم، فإدراج seeding كنشاط روتينيّ مضلّل.
    "orchard": FieldType(
        id="orchard",
        name_ar="بستان",
        geometry_kind="polygon",
        allowed_activities=(
            "pruning",
            "harvest",
            "pesticide",
            "irrigation",
            "fertilization",
            "observation",
        ),
        description_ar=(
            "بستان أشجار معمّرة؛ استُبعد البذر (seeding) لأنّ الزراعة لمرّة واحدة عند "
            "الإنشاء لا عمليّة موسميّة، وأُدرج التقليم كنشاط رئيسيّ."
        ),
    ),
    # بيت محميّ: بيئة مضبوطة — نفس أنشطة الزراعة لكن ضمن غطاء؛ نُبقي المجموعة المعتادة.
    "greenhouse": FieldType(
        id="greenhouse",
        name_ar="بيت محميّ",
        geometry_kind="polygon",
        allowed_activities=(
            "seeding",
            "fertilization",
            "irrigation",
            "pesticide",
            "pruning",
            "harvest",
            "observation",
        ),
        description_ar=("بيئة إنتاج مضبوطة (بيت محميّ)؛ تدعم دورة زراعة كاملة مع تقليم تحت الغطاء."),
    ),
    # مرعى: أرض رعويّة/علفيّة — أنشطة محدودة (لا بذر روتينيّ ولا تقليم)، تُسمح المراقبة.
    "pasture": FieldType(
        id="pasture",
        name_ar="مرعى",
        geometry_kind="polygon",
        allowed_activities=(
            "irrigation",
            "fertilization",
            "observation",
            "harvest",
        ),
        description_ar=("أرض رعويّة/علفيّة؛ أنشطة محدودة (الحشّ يُمثَّل بـ harvest) دون بذر روتينيّ."),
    ),
}


def list_field_types() -> tuple[FieldType, ...]:
    """يُرجع كلّ أنواع الحقول المعرّفة (بترتيب الكتالوج)."""
    return tuple(_CATALOG.values())


def get_field_type(field_type_id: str) -> FieldType | None:
    """يُرجع نوع الحقل بمعرّفه، أو None إن كان المعرّف مجهولاً."""
    return _CATALOG.get(field_type_id)


def activities_for(field_type_id: str) -> tuple[str, ...]:
    """يُرجع الأنشطة المسموح بها لنوع الحقل، أو () إن كان المعرّف مجهولاً."""
    ft = _CATALOG.get(field_type_id)
    return ft.allowed_activities if ft is not None else ()
