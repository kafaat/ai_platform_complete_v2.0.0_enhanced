"""
api/postharvest_advisor.py — إرشاد ما بعد الحصاد (التخزين وتقليل الفقد)

جانب جديد عملي وغير مطروق: الفقد بعد الحصاد سبب رئيسي لخسارة الحبوب في
الدول النامية واليمن — يُتلف جزء من المحصول لسوء التخزين رغم نجاح الموسم.
"من لا يخزّن جيّداً يخسر ما زرع".

المحاور (من أدبيّات وقاية الحبوب المخزونة + FAO):
  • عتبة الرطوبة الحرجة: القمح/الذرة ≤12-13% وإلّا حشرات وعفن
  • الآفات المخزنيّة الرئيسيّة (سوسة الأرز، خنفساء الخابرا، ثاقبة الحبوب)
  • الوقاية: نظافة الحبوب، الفحص الدوري، النيم كمادّة طبيعيّة
  • الذرة الشاميّة بأغلفتها (الكيزان) محميّة جزئيّاً من فراش الحبوب

⚠ إرشاد عامّ من أدبيّات موثّقة. لا يصف مبيدات تبخير (سامّة، تحتاج إشرافاً
متخصّصاً) — يوجّه للوقاية والطرق الآمنة، والكيميائي بإشراف فنّي عبر السلامة.
السياق اليمني: التخزين التقليدي شائع؛ تحسينه البسيط (تجفيف + نظافة + فحص)
يقلّل الفقد كثيراً دون تكلفة عالية.
"""
from __future__ import annotations

from typing import Dict, List, Optional


# عتبات الرطوبة القصوى للتخزين الآمن (% رطوبة الحبوب)
# المصدر: أدبيّات تخزين الحبوب — فوقها خطر حشرات وعفن
_MOISTURE_MAX: Dict[str, Dict] = {
    "wheat":   {"name_ar": "القمح", "safe_max": 12.0, "long_term": 12.0},
    "maize":   {"name_ar": "الذرة الشاميّة", "safe_max": 13.0, "long_term": 13.0},
    "sorghum": {"name_ar": "الذرة الرفيعة", "safe_max": 12.0, "long_term": 12.0},
    "millet":  {"name_ar": "الدخن", "safe_max": 12.0, "long_term": 12.0},
    "barley":  {"name_ar": "الشعير", "safe_max": 12.0, "long_term": 12.0},
}

_ALIASES = {
    "قمح": "wheat", "ذرة شامية": "maize", "ذرة شاميّة": "maize",
    "ذرة رفيعة": "sorghum", "دخن": "millet", "شعير": "barley",
}

# الآفات المخزنيّة الرئيسيّة للحبوب
_STORAGE_PESTS: List[Dict] = [
    {"name_ar": "سوسة الأرز", "scientific": "Sitophilus oryzae",
     "note_ar": "تثقب الحبّة وتتغذّى داخلها — من أخطر آفات الحبوب المخزونة."},
    {"name_ar": "خنفساء الخابرا", "scientific": "Trogoderma granarium",
     "note_ar": "يرقاتها تتلف الحبوب بشدّة، تقاوم الظروف الجافّة طويلاً."},
    {"name_ar": "ثاقبة الحبوب الصغرى", "scientific": "Rhyzopertha dominica",
     "note_ar": "تثقب الحبوب وتطحنها، تترك مسحوقاً."},
    {"name_ar": "فراش (عثّة) الحبوب", "scientific": "Sitotroga cerealella",
     "note_ar": "يرقاتها داخل الحبّة — الذرة الشاميّة بأغلفتها (الكيزان) محميّة جزئيّاً."},
]


def _resolve(crop: str) -> Optional[str]:
    c = crop.strip().lower()
    if c in _MOISTURE_MAX:
        return c
    return _ALIASES.get(crop.strip())


def check_storage_moisture(crop: str, moisture_pct: float) -> Dict:
    """يقيّم: هل رطوبة الحبوب آمنة للتخزين؟"""
    key = _resolve(crop)
    if not key:
        return {"supported": False,
                "message_ar": f"لا عتبة تخزين لـ«{crop}». المدعوم: "
                              + "، ".join(v["name_ar"] for v in _MOISTURE_MAX.values())}
    c = _MOISTURE_MAX[key]
    safe = c["safe_max"]
    if moisture_pct <= safe:
        status, status_ar = "safe", "✓ آمنة للتخزين"
        advice = f"رطوبة {moisture_pct:.1f}% ضمن الحدّ الآمن (≤{safe:.0f}%) لـ{c['name_ar']}."
    elif moisture_pct <= safe + 2:
        status, status_ar = "risky", "⚠ حدّيّة"
        advice = (f"رطوبة {moisture_pct:.1f}% أعلى من الحدّ الآمن (≤{safe:.0f}%). "
                  "جفّف أكثر قبل التخزين الطويل لتفادي الحشرات والعفن.")
    else:
        status, status_ar = "unsafe", "✗ غير آمنة"
        advice = (f"رطوبة {moisture_pct:.1f}% مرتفعة جدّاً (الحدّ ≤{safe:.0f}%). "
                  "التخزين الآن يعرّض المحصول لإصابة حشريّة وعفن — جفّف فوراً.")
    return {
        "supported": True,
        "crop_ar": c["name_ar"],
        "moisture_pct": moisture_pct, "safe_max_pct": safe,
        "status": status, "status_ar": status_ar, "advice_ar": advice,
    }


def storage_pests() -> Dict:
    """الآفات المخزنيّة الرئيسيّة للحبوب."""
    return {
        "pests": _STORAGE_PESTS,
        "note_ar": (
            "آفات تصيب الحبوب أثناء التخزين. الوقاية (تجفيف + نظافة + فحص دوري) "
            "خير من العلاج. الإصابة تزداد بطول التخزين والرطوبة العالية."
        ),
    }


def storage_best_practices(crop: Optional[str] = None) -> Dict:
    """أفضل ممارسات التخزين لتقليل الفقد بعد الحصاد."""
    practices = [
        {"topic_ar": "التجفيف", "detail_ar": "جفّف الحبوب لرطوبة ≤12-13% قبل التخزين (الأهمّ على الإطلاق)."},
        {"topic_ar": "النظافة", "detail_ar": "حبوب نظيفة خالية من الكسر والشوائب — الكسر بيئة مثاليّة للحشرات."},
        {"topic_ar": "المخزن", "detail_ar": "مكان جافّ غير رطب جيّد التهوية، بعيد عن مصادر الرطوبة."},
        {"topic_ar": "الفحص الدوري", "detail_ar": "افحص الحبوب كل أسبوعين-شهر للكشف المبكر عن أيّ إصابة."},
        {"topic_ar": "الوقاية الطبيعيّة", "detail_ar": "مسحوق بذور النيم يقلّل الإصابة الحشريّة طبيعيّاً (طريقة منخفضة التكلفة)."},
        {"topic_ar": "الحماية من القوارض والطيور", "detail_ar": "أغلق المخزن جيّداً؛ الذرة بأغلفتها لا تحميها من القوارض/الطيور."},
    ]
    result = {
        "practices_ar": practices,
        "principle_ar": (
            "التجفيف + النظافة + الفحص الدوري = ثلاثيّة تقليل الفقد. تحسينات "
            "بسيطة منخفضة التكلفة تحفظ موسماً كاملاً من التلف."
        ),
        "yemen_context_ar": (
            "الفقد بعد الحصاد سبب رئيسي لخسارة الحبوب في اليمن. التخزين التقليدي "
            "شائع — تحسينه البسيط (تجفيف جيّد + نظافة + فحص) يقلّل الفقد كثيراً "
            "دون تكلفة عالية، ويعزّز الأمن الغذائي."
        ),
        "chemical_note_ar": (
            "مبيدات التبخير (للإصابة الشديدة) سامّة وتحتاج إشرافاً متخصّصاً — "
            "راجع وحدة السلامة الكيميائيّة ولا تطبّقها دون خبرة فنّيّة."
        ),
        "disclaimer_ar": "إرشاد عامّ من أدبيّات تخزين الحبوب + FAO. يوجّه لا يفرض.",
    }
    if crop:
        key = _resolve(crop)
        if key:
            result["crop_moisture_ar"] = (
                f"عتبة الرطوبة الآمنة لـ{_MOISTURE_MAX[key]['name_ar']}: "
                f"≤{_MOISTURE_MAX[key]['safe_max']:.0f}%"
            )
    return result
