"""
api/ipm_advisor.py — الإدارة المتكاملة للآفات (IPM)

جانب جديد: تصنيف الآفات (scouting_pins) يحدّد "ما المشكلة"، لكن لا يرشد إلى
"كيف نديرها بنهج متكامل". الـIPM نهج متدرّج يقلّل الاعتماد على المبيدات:
  ١. الوقاية (مواعيد، دورة، أصناف) → ٢. المراقبة (فحص دوري، مصائد) →
  ٣. المكافحة الحيوية (أعداء طبيعيّون) → ٤. الكيميائيّة (ملاذ أخير، عند العتبة)

يركّز على دودة الحشد الخريفيّة — أخطر آفات الذرة الشاميّة (أكثر محاصيل اليمن)،
تصيب النجيليّات (ذرة، قمح، دخن، أرز)، وتنتشر سريعاً.

⚠ إرشاد عامّ من أدبيّات وقاية النبات + FAO/منظّمات إقليميّة. لا يصف مبيدات
محدّدة (السلامة عبر chemical_safety + التسجيل المحلّي). المكافحة الكيميائيّة
ملاذ أخير بإشراف فنّي. human-in-the-loop: المزارع يقرّر، الإرشاد يوجّه.
"""

from __future__ import annotations

from enum import Enum


class IPMStage(str, Enum):
    PREVENTION = "prevention"
    MONITORING = "monitoring"
    BIOLOGICAL = "biological"
    CHEMICAL = "chemical"  # ملاذ أخير


# قاعدة معرفة الآفات الرئيسيّة في اليمن + نهج IPM لكلّ منها
_PESTS: dict[str, dict] = {
    "fall_armyworm": {
        "name_ar": "دودة الحشد الخريفيّة",
        "scientific": "Spodoptera frugiperda",
        "hosts_ar": "النجيليّات: الذرة الشاميّة (الأكثر تفضيلاً)، الذرة الرفيعة، الدخن، القمح، الأرز",
        "severity_ar": "خطيرة جدّاً — تتكاثر بسرعة هائلة وتنتشر، خسائر اقتصاديّة كبيرة",
        "symptoms_ar": [
            "ثقوب غير منتظمة بالأوراق الحديثة",
            "آثار تغذية واضحة + مخلّفات يرقات داخل قلب النبات",
            "يرقة بعلامة تشبه حرف Y مقلوب أعلى الرأس (مميّزة)",
        ],
        "prevention_ar": [
            "الزراعة في الموعد الأمثل (تجنّب تأخير الذرة الشاميّة بعد منتصف يونيو)",
            "الدورة الزراعيّة (تجنّب تعاقب النجيليّات المتتالي)",
            "إزالة بقايا المحصول والحشائش العائلة",
        ],
        "monitoring_ar": [
            "الفحص الدوري المنتظم لقلب النباتات (خطّ الدفاع الأوّل)",
            "المصائد الفرمونيّة لرصد ظهور الفراشات مبكراً",
            "الكشف المبكر يمنح فرصة سيطرة أكبر",
        ],
        "biological_ar": [
            "متطفّل البيض تلينومس ريمس (Telenomus remus)",
            "أنواع الترايكوغراما (Trichogramma)",
            "المتطفّل اليرقي هابروبراكون (Habrobracon hebetor)",
            "المفترس أسد المنّ",
        ],
        "chemical_note_ar": (
            "ملاذ أخير عند تجاوز العتبة: الرشّ المبكّر لليرقات حديثة الفقس (8-10 أيام) "
            "يحقّق ~70% مكافحة. استشر السلامة الكيميائيّة والتسجيل المحلّي، وطبّق بإشراف فنّي."
        ),
        "economic_threshold_ar": "عند ملاحظة إصابة في 5-10% من النباتات في الفحص الدوري.",
    },
    "wheat_rust": {
        "name_ar": "صدأ القمح",
        "scientific": "Puccinia spp.",
        "hosts_ar": "القمح، الشعير",
        "severity_ar": "عالية — يقلّل المحصول وجودة الحبوب",
        "symptoms_ar": [
            "بثرات صفراء/برتقاليّة/بنّيّة على الأوراق والسيقان",
            "مسحوق يعلق باللمس",
            "اصفرار وجفاف مبكر للأوراق",
        ],
        "prevention_ar": [
            "زراعة أصناف مقاومة للصدأ",
            "تجنّب الإفراط في النيتروجين (يزيد القابليّة)",
            "الزراعة في الموعد المناسب لتفادي ذروة الإصابة",
        ],
        "monitoring_ar": [
            "الفحص الدوري للأوراق السفليّة (تظهر الإصابة أوّلاً)",
            "مراقبة الطقس: الرطوبة العالية + الحرارة المعتدلة تسرّع الانتشار",
        ],
        "biological_ar": [
            "لا مكافحة حيويّة عمليّة واسعة — التركيز على الأصناف المقاومة والوقاية",
        ],
        "chemical_note_ar": (
            "مبيدات فطريّة عند الإصابة المبكّرة وبظروف مواتية للانتشار. استشر "
            "السلامة الكيميائيّة والتسجيل المحلّي."
        ),
        "economic_threshold_ar": "عند أوّل ظهور للبثرات بظروف طقس مواتية للانتشار.",
    },
    "aphid": {
        "name_ar": "المنّ",
        "scientific": "Aphidoidea",
        "hosts_ar": "القمح، الشعير، الذرة، البرسيم، الخضروات",
        "severity_ar": "متوسّطة — يمتصّ العصارة وينقل فيروسات، إفرازات عسليّة",
        "symptoms_ar": [
            "تجمّعات حشرات صغيرة على الأوراق والقمم النامية",
            "تجعّد واصفرار الأوراق",
            "ندوة عسليّة لزجة + عفن أسود",
        ],
        "prevention_ar": [
            "تجنّب الإفراط في النيتروجين (يجذب المنّ)",
            "تشجيع التنوّع النباتي حول الحقل لإيواء الأعداء الطبيعيّين",
        ],
        "monitoring_ar": [
            "الفحص الدوري للقمم النامية والسطح السفلي للأوراق",
            "المصائد الصفراء اللاصقة",
        ],
        "biological_ar": [
            "أسد المنّ (Chrysoperla)",
            "أبو العيد / الدعسوقة (Coccinellidae)",
            "الدبابير المتطفّلة (Aphidius)",
        ],
        "chemical_note_ar": (
            "نادراً ما يلزم رشّ إن كانت الأعداء الطبيعيّة نشطة. عند الحاجة، استشر السلامة الكيميائيّة."
        ),
        "economic_threshold_ar": "عند تجمّعات كثيفة مع غياب الأعداء الطبيعيّين.",
    },
}

_ALIASES = {
    "دودة الحشد": "fall_armyworm",
    "دودة الحشد الخريفية": "fall_armyworm",
    "الحشد": "fall_armyworm",
    "armyworm": "fall_armyworm",
    "صدأ القمح": "wheat_rust",
    "صدأ": "wheat_rust",
    "rust": "wheat_rust",
    "منّ": "aphid",
    "المن": "aphid",
    "المنّ": "aphid",
}


def _resolve(pest: str) -> str | None:
    p = pest.strip().lower()
    if p in _PESTS:
        return p
    return _ALIASES.get(pest.strip())


def supported_pests() -> list[dict]:
    return [
        {
            "pest": k,
            "name_ar": v["name_ar"],
            "scientific": v["scientific"],
            "hosts_ar": v["hosts_ar"],
            "severity_ar": v["severity_ar"],
        }
        for k, v in _PESTS.items()
    ]


def ipm_plan(pest: str) -> dict:
    """خطّة الإدارة المتكاملة الكاملة لآفة (4 مراحل متدرّجة)."""
    key = _resolve(pest)
    if not key:
        return {
            "supported": False,
            "message_ar": f"لا خطّة IPM لـ«{pest}». المدعوم: "
            + "، ".join(v["name_ar"] for v in _PESTS.values()),
        }
    p = _PESTS[key]
    return {
        "supported": True,
        "pest": key,
        "name_ar": p["name_ar"],
        "scientific": p["scientific"],
        "hosts_ar": p["hosts_ar"],
        "severity_ar": p["severity_ar"],
        "symptoms_ar": p["symptoms_ar"],
        "ipm_ladder": [
            {
                "stage": "prevention",
                "stage_ar": "١. الوقاية (الأساس)",
                "actions_ar": p["prevention_ar"],
            },
            {
                "stage": "monitoring",
                "stage_ar": "٢. المراقبة والرصد",
                "actions_ar": p["monitoring_ar"],
            },
            {
                "stage": "biological",
                "stage_ar": "٣. المكافحة الحيويّة",
                "actions_ar": p["biological_ar"],
            },
            {
                "stage": "chemical",
                "stage_ar": "٤. الكيميائيّة (ملاذ أخير)",
                "actions_ar": [p["chemical_note_ar"]],
            },
        ],
        "economic_threshold_ar": p["economic_threshold_ar"],
        "philosophy_ar": (
            "ابدأ بالوقاية والمراقبة. المكافحة الكيميائيّة ملاذ أخير عند تجاوز "
            "العتبة الاقتصاديّة فقط — تقلّل التكلفة وتحمي الأعداء الطبيعيّين والبيئة."
        ),
        "disclaimer_ar": (
            "إرشاد عامّ من أدبيّات وقاية النبات + FAO. لا يصف مبيدات محدّدة — "
            "راجع السلامة الكيميائيّة والتسجيل المحلّي وطبّق بإشراف فنّي."
        ),
    }


def pests_for_crop(crop: str) -> dict:
    """يُرجع الآفات التي تصيب محصولاً معيّناً (للوقاية الاستباقيّة)."""
    crop_l = crop.strip().lower()
    crop_map = {
        "maize": "الذرة الشاميّة",
        "ذرة شامية": "الذرة الشاميّة",
        "ذرة شاميّة": "الذرة الشاميّة",
        "wheat": "القمح",
        "قمح": "القمح",
        "barley": "الشعير",
        "شعير": "الشعير",
        "sorghum": "الذرة الرفيعة",
        "millet": "الدخن",
        "دخن": "الدخن",
    }
    crop_ar = crop_map.get(crop_l) or crop_map.get(crop.strip())
    if not crop_ar:
        return {"supported": False, "message_ar": f"المحصول «{crop}» غير معروف."}

    matches = []
    for k, v in _PESTS.items():
        if crop_ar in v["hosts_ar"] or (crop_ar == "الذرة الشاميّة" and "الذرة" in v["hosts_ar"]):
            matches.append({"pest": k, "name_ar": v["name_ar"], "severity_ar": v["severity_ar"]})

    return {
        "supported": True,
        "crop_ar": crop_ar,
        "pests": matches,
        "note_ar": (
            "آفات محتملة لهذا المحصول. الفحص الدوري + الوقاية المبكرة خير من "
            "العلاج. لكلّ آفة خطّة IPM متدرّجة."
        ),
    }
