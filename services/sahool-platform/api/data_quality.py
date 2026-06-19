"""api/data_quality.py — تقييم جودة المدخلات (Source-of-Truth Honesty)

بدل أن تشتقّ الواجهة الثقة من تحليل نصوص `warnings_ar`، نُصدِر **حقولاً منظَّمة**
تصف جودة المدخلات صراحةً: قائمة الافتراضات (رموز آليّة + عربيّة)، درجة جودة
(low/medium/high)، و«ثقة» عدديّة.

⚠ «الثقة» هنا **مقياس اكتمال/جودة مدخلات شفّاف** (heuristic) لا فاصل ثقة إحصائيّ —
تُحسب بخصم جزاءات معلومة لكلّ افتراض. ما دام النموذج غير معايَر يمنيّاً
(`uncalibrated_model`) لا تبلغ الجودة «high» أبداً — صدق مقصود: لا ندّعي يقيناً
لا نملكه. نقيّ حتميّ (لا I/O).
"""

from __future__ import annotations

# الافتراضات المعروفة ⇒ وصف عربيّ للمستخدم.
ASSUMPTION_LABELS_AR: dict[str, str] = {
    "default_soil": "نوع تربة افتراضيّ (نسيج غير محدّد)",
    "estimated_root_depth": "عمق جذور تقديريّ",
    "no_moisture_sensor": "بلا حسّاس رطوبة ميدانيّ (Dr مُقدَّر لا مقيس)",
    "uncalibrated_model": "ثوابت غير معايَرة يمنيّاً (قد تختلف النتائج ±20٪)",
    "uniform_forecast": "تنبّؤ جوّيّ مبسّط موحّد",
    "policy_fallback": "تراجع السياسة لنقص مُدخَل",
}

# جزاء كلّ افتراض على «الثقة» (شفّاف، قابل للمعايرة). uncalibrated_model مهيمن:
# ما دام قائماً لا تبلغ الجودة «high» — لا ندّعي يقيناً قبل المعايرة.
_PENALTY: dict[str, float] = {
    "uncalibrated_model": 0.20,
    "default_soil": 0.15,
    "no_moisture_sensor": 0.10,
    "estimated_root_depth": 0.08,
    "policy_fallback": 0.07,
    "uniform_forecast": 0.05,
}

_CONFIDENCE_FLOOR = 0.30  # لا نزعم ثقة شبه معدومة (تبقى تقديراً مفيداً)


def assess_data_quality(assumptions: list[str]) -> dict:
    """يُحوّل قائمة افتراضات إلى حقول جودة منظَّمة — نقيّ حتميّ.

    يتجاهل الرموز المجهولة، ويزيل التكرار محافظاً على الترتيب. الجزاءات تُخصم من 1.0
    وتُقصّ عند أرضيّة. الجودة: high ≥0.8 / medium ≥0.5 / وإلّا low.
    """
    seen = [a for a in dict.fromkeys(assumptions) if a in _PENALTY]
    conf = 1.0
    for a in seen:
        conf -= _PENALTY[a]
    conf = max(_CONFIDENCE_FLOOR, min(1.0, conf))
    quality = "high" if conf >= 0.8 else "medium" if conf >= 0.5 else "low"
    return {
        "confidence": round(conf, 2),
        "data_quality": quality,
        "assumptions": seen,
        "assumptions_ar": [ASSUMPTION_LABELS_AR[a] for a in seen],
        "calibrated": False,
    }
