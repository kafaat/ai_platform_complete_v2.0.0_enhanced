"""api/irrigation_method.py — أثر طريقة الريّ (Irrigation Method) #387

طريقة الريّ (غمر/أخاديد/مرشّات/محوري/تقطير) تؤثّر جوهريّاً في قرارات الريّ:
  • **كفاءة التطبيق Ea**: الماء المسحوب فعلاً = الصافي ÷ Ea (الغمر يهدر، التقطير أكفأ)
    ⇒ يصحّح تكلفة الماء وسعة الآبار (لا نُقلّل تكلفة الغمر بتحويل مم→م³ بلا كفاءة).
  • **نمط البلل (wetted_fraction) وعامل التبخّر Ke**: التقطير يبلّل جزءاً ⇒ تبخّر أقلّ.
  • **سقف الدفعة الافتراضيّ**: التقطير دفعات صغيرة متكرّرة؛ الغمر كبيرة متباعدة.
  • **الطاقة**: المضغوط (محوري/مرشّات) يحتاج ضخّاً؛ الجاذبيّ (غمر) أقلّ.

نقيّ حتميّ (لا I/O). ⚠ القيم نطاقات FAO-56/أدبيّات عامّة — **ليست مُعايَرة** لكلّ نظام/
منطقة (موسومة calibrated=False، تُحقَن لاحقاً عبر طبقة المعايرة الإقليميّة).
"""

from __future__ import annotations

# ملامح الطرق — منتصفات FAO-56 (جدول كفاءات التطبيق) + أدبيّات. ⚠ غير معايَرة.
# (Ea, wetted_fraction, ke_factor, typical_max_application_mm, pressurized)
_METHOD_PROFILES: dict[str, tuple[float, float, float, float, bool]] = {
    "flood": (0.55, 1.0, 1.0, 100.0, False),
    "furrow": (0.60, 0.6, 0.9, 80.0, False),
    "sprinkler": (0.75, 1.0, 1.0, 30.0, True),
    "pivot": (0.85, 1.0, 0.95, 25.0, True),
    "drip": (0.90, 0.4, 0.7, 8.0, True),
}
# مجهول ⇒ افتراضيّ محافظ (كفاءة متوسّطة) موسوم.
_GENERIC = (0.70, 1.0, 1.0, 30.0, True)

METHOD_NAMES_AR: dict[str, str] = {
    "flood": "غمر",
    "furrow": "أخاديد",
    "sprinkler": "مرشّات",
    "pivot": "محوري",
    "drip": "تقطير",
}
_METHOD_ALIASES: dict[str, str] = {
    "غمر": "flood",
    "تغريق": "flood",
    "أخاديد": "furrow",
    "اخاديد": "furrow",
    "خطوط": "furrow",
    "مرشّات": "sprinkler",
    "مرشات": "sprinkler",
    "رش": "sprinkler",
    "محوري": "pivot",
    "بيفوت": "pivot",
    "تقطير": "drip",
    "نقطي": "drip",
}


def normalize_method(method: str | None) -> tuple[str, bool]:
    """يُرجع (مفتاح الطريقة، هل معروفة). يطبّع العربيّة والحالة."""
    if not method:
        return "generic", False
    key = method.strip().lower()
    key = _METHOD_ALIASES.get(method.strip(), _METHOD_ALIASES.get(key, key))
    return (key, True) if key in _METHOD_PROFILES else ("generic", False)


def method_profile(method: str | None) -> dict:
    """ملامح طريقة الريّ — نقيّ حتميّ. مجهولة ⇒ افتراضيّ محافظ موسوم."""
    key, known = normalize_method(method)
    ea, wetted, ke, max_app, pressurized = _METHOD_PROFILES.get(key, _GENERIC)
    return {
        "method": key,
        "method_ar": METHOD_NAMES_AR.get(key, "عامّ"),
        "known": known,
        "application_efficiency": ea,
        "wetted_fraction": wetted,
        "ke_factor": ke,
        "typical_max_application_mm": max_app,
        "pressurized": pressurized,
        "calibrated": False,
        "warnings_ar": (
            [] if known else ["طريقة ريّ غير معروفة — كفاءة افتراضيّة محافظة؛ حدّد الطريقة للدقّة"]
        )
        + ["كفاءات FAO عامّة غير معايَرة لكلّ نظام/منطقة"],
    }


def gross_irrigation_mm(
    net_mm: float,
    method: str | None = None,
    application_efficiency: float | None = None,
) -> float:
    """الماء الإجماليّ المسحوب = الصافي ÷ كفاءة التطبيق — نقيّ حتميّ.

    تُستعمَل الكفاءة الممرَّرة إن وُجدت، وإلّا كفاءة الطريقة. هذا ما يجب أن يدخل تكلفة
    الماء/سعة الآبار (لا الصافي). كفاءة ≤0 أو غياب ⇒ كفاءة الطريقة/العامّة.
    """
    ea = application_efficiency
    if ea is None or ea <= 0:
        ea = method_profile(method)["application_efficiency"]
    return round(net_mm / ea, 2) if ea > 0 else round(net_mm, 2)
