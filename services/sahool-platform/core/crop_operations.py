"""core/crop_operations.py — تقويم العمليّات الحقليّة المرتبط بمراحل النموّ.

يربط كلّ مرحلة نموّ طوريّة (FAO-56: initial/development/mid/late) بقائمة العمليّات
الحقليّة المُوصى بها لها (تقويم عمليّات مُهيكَل لكلّ مرحلة)، بناءً على فينولوجيا
بطاقة المحصول (core.crop_cards.loader → phenology.stages). أغنى من ``key_action_ar``
المفردة في البطاقة: قائمة عمليّات مُصنَّفة لكلّ مرحلة، كلّ عمليّة بفئة وتوقيت وملاحظة.

دالّة نقيّة بالكامل (لا قاعدة، لا I/O، لا شبكة) — تُختبَر offline. تعتمد فقط على
``core.crop_cards.loader`` و``core.season_phenology``. خرائط العمليّات محايدة الموقع
ومستندة إلى ممارسات زراعيّة عامّة مقبولة (FAO-56 stage agronomy) — بلا جُرعات كيميائيّة
محصوليّة (تلك تعيش في وحدات أخرى). المحصول بلا فينولوجيا ⇒ مراحل فارغة (صدق: لا تلفيق).

غمزة العائلة (crop_family): البقوليّات (legume) تثبّت النيتروجين (Rhizobium) فاحتياجها
النيتروجينيّ منخفض (دفعة بادئة فقط)؛ الحبوب (cereal) تستفيد من تسميد آزوتيّ تعلويّ
(top-dressing) عند التفريع. تُطبَّق بحذر وموثّقة، ولا تُغيّر العمليّات الأساسيّة.
"""

from __future__ import annotations

from core.crop_cards.loader import load_crop_card
from core.season_phenology import current_stage

# المصدر المرجعيّ العامّ للخرائط — ممارسة زراعيّة عامّة (لا معايرة/إنتاج/جُرعات).
_SOURCE_AR = "ممارسة زراعيّة عامّة (FAO-56 stage agronomy)"

# الفئات المعتمدة للعمليّات (category ∈ هذه المجموعة).
_VALID_CATEGORIES = frozenset(
    {
        "land_prep",
        "sowing",
        "fertilization",
        "irrigation",
        "weeding",
        "protection",  # مسح الآفات والمكافحة المتكاملة (IPM scouting)
        "harvest",
    }
)

# الترجمة العربيّة للفئات (category_ar) — لعرض واجهة موحَّد.
_CATEGORY_AR: dict[str, str] = {
    "land_prep": "تجهيز الأرض",
    "sowing": "البذار",
    "fertilization": "التسميد",
    "irrigation": "الريّ",
    "weeding": "العزيق ومكافحة الحشائش",
    "protection": "المسح ومكافحة الآفات (IPM)",
    "harvest": "الحصاد",
}


def _op(category: str, operation_ar: str, timing_ar: str, note_ar: str) -> dict:
    """يبني سجلّ عمليّة موحَّداً: {category, category_ar, operation_ar, timing_ar, note_ar}."""
    return {
        "category": category,
        "category_ar": _CATEGORY_AR[category],
        "operation_ar": operation_ar,
        "timing_ar": timing_ar,
        "note_ar": note_ar,
    }


# ─── الخريطة الأساسيّة: مرحلة طوريّة → قائمة عمليّات مُصنَّفة (محايدة الموقع) ───
# مبنيّة على ممارسات زراعيّة عامّة مقبولة عالميّاً، بلا جُرعات/منتجات محصوليّة.
_BASE_OPERATIONS: dict[str, list[dict]] = {
    # الإنبات والتأسيس: تجهيز مهد البذرة، بذار، ريّ تأسيس خفيف متكرّر، مكافحة حشائش مبكّرة.
    "initial": [
        _op(
            "land_prep",
            "تجهيز مهد البذرة وتسوية الأرض وتأمين الصرف",
            "قبل البذار",
            "مهد ناعم مستوٍ يحسّن انتظام الإنبات والصرف.",
        ),
        _op(
            "sowing",
            "البذار على العمق والكثافة الموصى بهما",
            "بداية المرحلة (يوم 0)",
            "عمق وكثافة مناسبان يحدّدان انتظام الوقفة الأولى.",
        ),
        _op(
            "irrigation",
            "ريّ تأسيس خفيف متكرّر لضمان إنبات منتظم",
            "من البذار حتى اكتمال الإنبات",
            "رطوبة سطحيّة ثابتة دون إغراق؛ الإفراط يخنق البادرات.",
        ),
        _op(
            "weeding",
            "مكافحة الحشائش المبكّرة (يدويّة/ميكانيكيّة خفيفة)",
            "بعد ظهور البادرات",
            "المنافسة المبكّرة للحشائش أشدّ ضرراً على الوقفة الفتيّة.",
        ),
        _op(
            "protection",
            "مسح ميدانيّ مبكّر لآفات البادرات وأضرار الإنبات",
            "أسبوعيّاً خلال المرحلة",
            "المسح المبكّر يكشف فجوات الوقفة وآفات البادرة باكراً.",
        ),
    ],
    # النموّ الخضري: تسميد آزوتيّ، عزيق، مسح آفات.
    "development": [
        _op(
            "fertilization",
            "تسميد (آزوتيّ بحسب احتياج المحصول) لدعم النموّ الخضري",
            "خلال النموّ الخضري النشط",
            "يُعدَّل المعدّل بحسب العائلة المحصوليّة وتحليل التربة.",
        ),
        _op(
            "irrigation",
            "ريّ منتظم متصاعد مع نموّ المجموع الخضري",
            "طوال المرحلة",
            "زيادة تدريجيّة مع تزايد المساحة الورقيّة (Kc صاعد).",
        ),
        _op(
            "weeding",
            "عزيق ومكافحة الحشائش وفلق القشرة السطحيّة",
            "منتصف النموّ الخضري",
            "العزيق يحسّن التهوية ويقلّل منافسة الحشائش قبل التغطية الكاملة.",
        ),
        _op(
            "protection",
            "مسح آفات النموّ الخضري والمكافحة المتكاملة (IPM)",
            "أسبوعيّاً خلال المرحلة",
            "اعتماد عتبات المسح قبل أيّ تدخّل (IPM)؛ تفاصيل الآفات إقليميّة.",
        ),
    ],
    # التزهير وتكوين الثمار (الطور التكاثريّ): ذروة الريّ — لا إجهاد، مسح آفات الإزهار/العقد.
    "mid": [
        _op(
            "irrigation",
            "ذروة الاحتياج المائيّ — ريّ كافٍ بلا إجهاد (peak / no-stress)",
            "طوال التزهير والعقد",
            "الطور الأكثر حساسيّة: الإجهاد المائيّ أو الحراريّ يُسقط الأزهار/العقد.",
        ),
        _op(
            "protection",
            "مسح مكثّف لآفات الإزهار والعقد والمكافحة المتكاملة (IPM)",
            "أسبوعيّاً (أو أكثف) خلال التزهير",
            "حماية الأعضاء التكاثريّة حرجة للغلّة؛ كثّف المسح في هذه النافذة.",
        ),
        _op(
            "fertilization",
            "تسميد داعم للعقد (بوتاسيّ/فوسفاتيّ بحسب الاحتياج)",
            "بداية التزهير/العقد",
            "يدعم امتلاء/تثبيت الثمار؛ يُعدَّل بحسب تحليل التربة.",
        ),
        _op(
            "weeding",
            "إبقاء الحقل نظيفاً من الحشائش دون إزعاج الجذور",
            "حسب الحاجة",
            "تجنّب العزيق العميق قرب الأزهار لئلّا يُحدِث إجهاداً.",
        ),
    ],
    # امتلاء البذور والنضج: تقليل الريّ، جاهزيّة الحصاد.
    "late": [
        _op(
            "irrigation",
            "تقليل الريّ تدريجيّاً نحو النضج (تجفيف مُتحكَّم)",
            "مع بدء النضج",
            "تقليل الريّ يسرّع النضج ويحسّن جفاف الحبّ قبل الحصاد.",
        ),
        _op(
            "protection",
            "مسح آفات النضج/التخزين قبل الحصاد",
            "قبل الحصاد",
            "كشف آفات ما قبل الحصاد يحمي جودة المحصول المخزَّن.",
        ),
        _op(
            "harvest",
            "تقييم جاهزيّة الحصاد والحصاد عند النضج الفسيولوجيّ",
            "عند اكتمال النضج",
            "الحصاد في التوقيت الأمثل يقلّل فقد الغلّة والجودة.",
        ),
    ],
}


def _family_nuance(stage: str, crop_family: str | None) -> list[dict]:
    """عمليّات إضافيّة بحسب العائلة المحصوليّة (غمزة modest موثّقة) — أو [] إن لا غمزة.

    - legume (تثبيت النيتروجين عبر Rhizobium): النموّ الخضري بنيتروجين منخفض (دفعة بادئة فقط).
    - cereal (الحبوب): تسميد آزوتيّ تعلويّ (top-dressing) عند التفريع/الاستطالة.
    تُطبَّق فقط في مرحلة النموّ الخضري (development) حيث يختلف نظام النيتروجين بوضوح.
    """
    if not crop_family or stage != "development":
        return []
    fam = crop_family.lower()
    if fam.startswith("legume"):
        return [
            _op(
                "fertilization",
                "خفض التسميد الآزوتيّ — البقوليّة تثبّت النيتروجين (Rhizobium): دفعة بادئة فقط",
                "بداية النموّ الخضري",
                "تثبيت النيتروجين الحيويّ يغطّي معظم الاحتياج؛ الإفراط الآزوتيّ يضرّ العقد الجذريّة.",
            )
        ]
    if fam.startswith("cereal"):
        return [
            _op(
                "fertilization",
                "تسميد آزوتيّ تعلويّ (top-dressing) عند التفريع",
                "طور التفريع/الاستطالة",
                "الحبوب تستجيب لتقسيط النيتروجين؛ دفعة تعلويّة عند التفريع تدعم عدد السنابل.",
            )
        ]
    return []


def stage_operations(stage: str, crop_family: str | None = None) -> list[dict]:
    """عمليّات مرحلة طوريّة مُسمّاة (initial/development/mid/late) مع غمزة العائلة.

    يُرجع قائمة عمليّات، كلّ منها {category, category_ar, operation_ar, timing_ar, note_ar}.
    المرحلة المجهولة ⇒ [] (صدق: لا عمليّات مُلفَّقة). تُدمَج غمزة crop_family إن طُبِّقت.
    """
    base = _BASE_OPERATIONS.get(stage)
    if base is None:
        return []
    ops = [dict(op) for op in base]
    ops.extend(_family_nuance(stage, crop_family))
    return ops


def crop_operations_calendar(crop_id: str) -> dict:
    """تقويم العمليّات الكامل لمحصول: فينولوجيا البطاقة × عمليّات كلّ مرحلة.

    يجمع مراحل بطاقة المحصول (load_crop_card → phenology.stages) مع stage_operations،
    مُعيداً {crop_id, crop_family, stages:[{stage, name_ar, day_start, day_end, operations}],
    source_ar}. المحصول بلا فينولوجيا (أو غير موجود) ⇒ قائمة stages فارغة (صدق).
    """
    card = load_crop_card(crop_id)
    crop_family = (card or {}).get("crop_family")
    raw_stages = (card or {}).get("phenology", {}).get("stages", []) if card else []
    stages: list[dict] = []
    for st in raw_stages:
        stages.append(
            {
                "stage": st["stage"],
                "name_ar": st.get("name_ar"),
                "day_start": st.get("day_start"),
                "day_end": st.get("day_end"),
                "operations": stage_operations(st["stage"], crop_family),
            }
        )
    return {
        "crop_id": crop_id,
        "crop_family": crop_family,
        "stages": stages,
        "source_ar": _SOURCE_AR,
    }


def current_stage_operations(crop_id: str, days_since_sowing: int | None) -> dict:
    """عمليّات المرحلة الحاليّة للمحصول (season_phenology.current_stage) لعمر معطى.

    يُرجع {available: True, crop_id, crop_family, stage, name_ar, day_start, day_end,
    operations, source_ar} حين تُعرَف المرحلة، و{available: False} حين تُجهَل (لا crop_id/
    عمر، لا فينولوجيا، أو تجاوز العمر آخر مرحلة — صدق: لا مرحلة مُلفَّقة).
    """
    st = current_stage(crop_id, days_since_sowing)
    if st is None:
        return {"available": False}
    card = load_crop_card(crop_id)
    crop_family = (card or {}).get("crop_family")
    return {
        "available": True,
        "crop_id": crop_id,
        "crop_family": crop_family,
        "stage": st["stage"],
        "name_ar": st.get("name_ar"),
        "day_start": st.get("day_start"),
        "day_end": st.get("day_end"),
        "operations": stage_operations(st["stage"], crop_family),
        "source_ar": _SOURCE_AR,
    }
