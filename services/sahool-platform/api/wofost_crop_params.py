"""
api/wofost_crop_params.py — دليل بارامترات WOFOST عبر المحاصيل

يطبّق إطار "التحليل التقني لتطبيقات WOFOST عبر المحاصيل" (irripro، مايو ٢٠٢٦).

المشكلة التي يحلّها:
  منصّة سهول تروّج محاصيل شجريّة/خضريّة (حمضيات، نخيل، عنب، بطاطس) لكنّ
  محرّك GDD/النموّ يدعم محاصيل حوليّة فقط (قمح/شعير/ذرة...). فتح محصول شجري
  يسقط على بارامترات القمح — خطأ علمي (الأشجار دورة موسميّة معمّرة لا حوليّة).

ما يوفّره هذا الدليل:
  • تصنيف نوع نموذج المحصول (حولي/شجرة معمّرة/خضار محميّة)
  • البارامترات الرئيسيّة التي تحتاج تعديلاً عند الانتقال من القمح (الأساس)
    لكلّ نوع، مع المدى ومصدره من المستند
  • نسبة التغيير المتوقّعة ودرجة الثقة (R²) — من جدول المستند
  • تحذيرات الحدود (ندرة البارامترات، حاجة المعايرة الميدانيّة)

⚠ صدق علمي حاسم:
  هذه **بارامترات إرشاديّة للمعايرة**، لا قيم نهائيّة جاهزة. المستند نفسه
  ينصّ أنّ التحويل يحتاج معايرة ميدانيّة (RMSE < 15%) وأنّ البارامترات
  الفيزيولوجيّة لبعض المحاصيل تفتقر لبيانات عامّة. لا نعرض رقماً كأنّه
  مُعايَر لليمن — نعرضه كنقطة بداية موسومة بمصدرها ومداها.
"""
from __future__ import annotations

from typing import Dict


# نوع نموذج المحصول → يحدّد مدى التعديل المطلوب عن نموذج القمح الأساسي
# (نسب التغيير من جدول المستند: القمح ٠٪، الحمضيات ٤٠-٦٠٪، الفلفل ٣٠-٥٠٪...)
_CROP_MODEL_TYPE = {
    # حوليّة حبّيّة — النموذج الأساسي يعمل مباشرة (تغيير ~٠٪)
    "wheat": "annual_cereal", "barley": "annual_cereal",
    "maize": "annual_cereal", "sorghum": "annual_cereal",
    "millet": "annual_cereal", "rice": "annual_cereal",
    "قمح": "annual_cereal", "شعير": "annual_cereal",
    "ذرة": "annual_cereal", "ذرة رفيعة": "annual_cereal",
    # أشجار مثمرة معمّرة — تحتاج إعادة تشكيل المناخ + التوزيع (تغيير ٤٠-٦٠٪)
    "citrus": "perennial_tree", "date_palm": "perennial_tree",
    "grape": "perennial_tree", "olive": "perennial_tree",
    "pomegranate": "perennial_tree", "almond": "perennial_tree",
    "fig": "perennial_tree", "mango": "perennial_tree",
    "حمضيات": "perennial_tree", "نخيل": "perennial_tree",
    "عنب": "perennial_tree", "زيتون": "perennial_tree",
    "رمّان": "perennial_tree", "لوز": "perennial_tree",
    # خضار/ثمريّة — تفصيل العمليّات الفسيولوجيّة + توسيع التغذية (تغيير ٣٠-٥٠٪)
    "tomato": "vegetable_fruit", "pepper": "vegetable_fruit",
    "cucumber": "vegetable_fruit", "potato": "tuber",
    "طماطم": "vegetable_fruit", "فلفل": "vegetable_fruit",
    "خيار": "vegetable_fruit", "بطاطس": "tuber",
}

# إطار التعديل لكلّ نوع — من جداول المستند (البارامترات + المدى + المصدر)
_ADAPTATION_FRAMEWORK = {
    "annual_cereal": {
        "name_ar": "محصول حبّي حولي",
        "change_pct": "0%",
        "typical_r2": "0.85–0.95",
        "data_need_gb": "0.1–0.5",
        "summary_ar": "النموذج الأساسي (القمح) يعمل مباشرة — أدنى تعديل.",
        "key_params": [],
        "phenology_ar": "دورة بذار→حصاد واحدة موسميّة.",
    },
    "perennial_tree": {
        "name_ar": "شجرة مثمرة معمّرة",
        "change_pct": "40–60%",
        "typical_r2": "0.75–0.85",
        "data_need_gb": "10–50",
        "summary_ar": (
            "تحتاج إعادة تشكيل الفينولوجيا (دورة معمّرة لا حوليّة) + "
            "إعادة بناء توزيع المستحاثات نحو الثمار."
        ),
        "key_params": [
            {"param": "PHINT_CYCLE", "name_ar": "دورة النموّ الفينولوجي",
             "note_ar": "استبدال دورة البذار→الحصاد بدورة معمّرة (سكون→تفتّح→إزهار→عقد→نضج)",
             "source_ar": "حالة الحمضيات Chongqing"},
            {"param": "RDMSOL", "name_ar": "أقصى عمق جذور",
             "range": "2.5–3.0 م", "default_wheat": "1.2 م",
             "note_ar": "الأشجار جذورها أعمق بكثير — يؤثّر على استخراج الماء",
             "source_ar": "حالة عنب شينجيانغ"},
            {"param": "CVO", "name_ar": "كفاءة تحويل المستحاثات للتخزين",
             "range": "0.5–0.7", "default_wheat": "0.4–0.6",
             "note_ar": "نحو أعضاء تخزين الثمار", "source_ar": "حالة الحمضيات"},
            {"param": "TMNFTB", "name_ar": "عتبة تصحيح الحرارة المنخفضة",
             "range": "~35°C", "note_ar": "وحدة إجهاد حراري للحرّ العالي (مهمّ للجوف)",
             "source_ar": "حالة الحمضيات"},
        ],
        "phenology_ar": "دورة موسميّة معمّرة متكرّرة (لا بذار→حصاد).",
    },
    "vegetable_fruit": {
        "name_ar": "خضار ثمريّة",
        "change_pct": "30–50%",
        "typical_r2": "0.70–0.80",
        "data_need_gb": "5–20",
        "summary_ar": "تفصيل العمليّات الفسيولوجيّة + توسيع وحدة التغذية.",
        "key_params": [
            {"param": "Photoperiod", "name_ar": "حسّاسيّة الفترة الضوئيّة",
             "range": "يوم حرج ~12 ساعة", "note_ar": "بعض الخضار حسّاسة لطول النهار",
             "source_ar": "حالة الفلفل"},
            {"param": "NITRO", "name_ar": "عتبة إجهاد النيتروجين",
             "range": "20 mg/kg", "default_wheat": "10 mg/kg",
             "note_ar": "الخضار أكثر حساسيّة لنقص N", "source_ar": "حالة الفلفل"},
            {"param": "CFET", "name_ar": "عامل تصحيح التبخّر",
             "range": "500–600", "default_wheat": "250–400",
             "note_ar": "الخضار عالية التبخّر — يضبط احتياج الماء",
             "source_ar": "حالة طماطم شاندونغ"},
        ],
        "phenology_ar": "دورة حوليّة لكن بمراحل ثمريّة مفصّلة.",
    },
    "tuber": {
        "name_ar": "محصول درنيّ",
        "change_pct": "35–55%",
        "typical_r2": "0.75–0.85",
        "data_need_gb": "3–10",
        "summary_ar": "محاكاة الأعضاء التخزينيّة (الدرنات) + تعديل جذري ديناميكي.",
        "key_params": [
            {"param": "TB", "name_ar": "الحرارة المثلى لتضخّم الدرنات",
             "range": "18–22°C", "note_ar": "علاقة غير خطّيّة بين التضخّم والحرارة",
             "source_ar": "حالة بطاطس بولندا"},
            {"param": "ROOTGROW", "name_ar": "سرعة نموّ الجذور",
             "note_ar": "تعديل ديناميكي لنسبة رطوبة التربة", "source_ar": "حالة البطاطس"},
            {"param": "HI", "name_ar": "مؤشّر المحصول (الحصاد)",
             "range": "0.6–0.8", "default_wheat": "0.4–0.5",
             "note_ar": "نسبة الدرنات للكتلة الكلّيّة أعلى", "source_ar": "حالة البطاطس"},
        ],
        "phenology_ar": "دورة حوليّة مع طور تكوين درنات حرج.",
    },
}


def crop_model_type(crop: str) -> str:
    """يصنّف نوع نموذج المحصول (يحدّد مدى التعديل عن القمح الأساسي)."""
    return _CROP_MODEL_TYPE.get(crop.lower()) or _CROP_MODEL_TYPE.get(crop) or "perennial_tree"


def wofost_adaptation_guidance(crop: str) -> Dict:
    """دليل تعديل بارامترات WOFOST لمحصول مستهدف (عن النموذج الأساسي).

    يُرجع نوع النموذج، نسبة التغيير المتوقّعة، البارامترات الرئيسيّة التي
    تحتاج تعديلاً (مع المدى والمصدر)، وتحذيرات الحدود — كلّها إرشاديّة
    للمعايرة لا قيم نهائيّة.
    """
    known = crop.lower() in _CROP_MODEL_TYPE or crop in _CROP_MODEL_TYPE
    mtype = crop_model_type(crop)
    fw = _ADAPTATION_FRAMEWORK[mtype]

    return {
        "crop": crop,
        "crop_recognized": known,
        "model_type": mtype,
        "model_type_ar": fw["name_ar"],
        "expected_change_pct": fw["change_pct"],
        "typical_validation_r2": fw["typical_r2"],
        "data_requirement_gb": fw["data_need_gb"],
        "phenology_ar": fw["phenology_ar"],
        "adaptation_summary_ar": fw["summary_ar"],
        "key_parameters": fw["key_params"],
        "base_model_ar": "القمح (النموذج الأساسي الأكثر معايرةً وتحقّقاً).",
        "disclaimer_ar": (
            "هذه بارامترات إرشاديّة للمعايرة من حالات منشورة، لا قيم نهائيّة "
            "مُعايَرة لليمن. التحويل يحتاج معايرة ميدانيّة (هدف RMSE < 15%) "
            "ببيانات الصنف والإقليم المحلّيّين. "
            + ("" if known else
               "هذا المحصول غير مصنّف صراحةً — عُومل افتراضيّاً كشجرة معمّرة، تحقّق يدويّاً.")
        ),
        "limitations_ar": [
            "البارامترات الفيزيولوجيّة لبعض المحاصيل (الاستوائيّة التجاريّة) "
            "تفتقر لبيانات عامّة وتحتاج تجارب ميدانيّة محلّيّة.",
            "افتراض تجانس التربة قد لا يطابق الحقل الفعلي — يحتاج تصحيحاً مكانيّاً.",
            "كلّما زادت نسبة التغيير عن القمح، انخفضت الثقة (R²) وزاد الطلب على البيانات.",
        ],
    }


def list_supported_crop_types() -> Dict:
    """يعرض أنواع نماذج المحاصيل المدعومة وإطار كلّ منها."""
    return {
        "model_types": {
            k: {"name_ar": v["name_ar"], "change_pct": v["change_pct"],
                "typical_r2": v["typical_r2"]}
            for k, v in _ADAPTATION_FRAMEWORK.items()
        },
        "note_ar": (
            "كلّ نوع يحتاج مدى تعديل مختلفاً عن نموذج القمح الأساسي. "
            "القمح ٠٪ (يعمل مباشرة)، الأشجار ٤٠-٦٠٪ (الأعقد)."
        ),
    }
