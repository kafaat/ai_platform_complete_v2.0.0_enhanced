"""
api/salinity_management.py — إدارة ملوحة التربة والمياه

جانب جديد عملي: crop_suitability يقول "هل المحصول يتحمّل الملوحة"، لكن لا
يرشد إلى **كيف يدير المزارع** تربةً أو ماءً مالحاً. الملوحة مشكلة **محلّيّة
في مناطق محدّدة** (لا تعمّم على كلّ اليمن): بعض مناطق الجوف، السهول الساحليّة،
ومناطق الريّ الجوفي المكثّف حيث المناخ الجافّ والتبخّر العالي يراكمان الأملاح.

⚠ هذه الأداة **تشخيصيّة عند الحاجة** — تُستخدم فقط حين تُظهر تحاليل التربة/الماء
ملوحةً فعليّة في حقل معيّن. كثير من أراضي اليمن (المرتفعات، المناطق المطريّة)
لا تعاني ملوحةً تُذكر.

يقدّم:
  • تصنيف شدّة الملوحة (EC) ومخاطرها
  • احتياج الغسيل (Leaching Requirement) لطرد الأملاح من منطقة الجذور
  • تقييم خطر الصوديوم (SAR) على بنية التربة
  • توصيات إدارة عمليّة (غسيل، تصريف، اختيار محصول متحمّل)

⚠ القيم من معايير FAO-29 (Ayers & Westcot) لجودة مياه الريّ. إرشاد يحتاج
معايرة محلّيّة (نوع التربة، التصريف). المختبر يحكم القيم الفعليّة. توجّه لا تفرض.

السياق: في المناطق المتأثّرة بالملوحة، المياه الجوفيّة الشحيحة قد تكون مالحة.
الغسيل يستهلك ماءً
إضافيّاً (معضلة في بلد شحيح) → موازنة دقيقة بين طرد الملح وتوفير الماء.
"""

from __future__ import annotations


# تصنيف ملوحة التربة (ECe بالـdS/m) — معايير FAO
def classify_soil_salinity(ece_dsm: float) -> dict:
    """يصنّف شدّة ملوحة التربة (ECe) ومخاطرها على المحاصيل."""
    if ece_dsm < 2:
        cls, cls_ar = "non_saline", "غير مالحة"
        effect = "لا أثر يُذكر على معظم المحاصيل."
    elif ece_dsm < 4:
        cls, cls_ar = "slightly_saline", "ملوحة خفيفة"
        effect = "تتأثّر المحاصيل الحسّاسة جدّاً فقط."
    elif ece_dsm < 8:
        cls, cls_ar = "moderately_saline", "ملوحة متوسّطة"
        effect = "تتأثّر كثير من المحاصيل؛ اختر المتحمّلة (شعير، نخيل)."
    elif ece_dsm < 16:
        cls, cls_ar = "strongly_saline", "ملوحة شديدة"
        effect = "المحاصيل المتحمّلة فقط تنتج؛ يلزم غسيل وتصريف."
    else:
        cls, cls_ar = "very_strongly_saline", "ملوحة شديدة جدّاً"
        effect = "قليل جدّاً من المحاصيل ينجح؛ إصلاح مكثّف ضروري."

    return {
        "ece_dsm": ece_dsm,
        "class": cls,
        "class_ar": cls_ar,
        "effect_ar": effect,
    }


# تصنيف ملوحة ماء الريّ (ECw بالـdS/m) — FAO-29
def classify_water_salinity(ecw_dsm: float) -> dict:
    """يصنّف صلاحيّة ماء الريّ حسب ملوحته."""
    if ecw_dsm < 0.7:
        risk, risk_ar = "none", "لا قيود"
    elif ecw_dsm < 3.0:
        risk, risk_ar = "slight_moderate", "قيود خفيفة-متوسّطة"
    else:
        risk, risk_ar = "severe", "قيود شديدة"
    return {
        "ecw_dsm": ecw_dsm,
        "risk": risk,
        "risk_ar": risk_ar,
        "note_ar": (
            "ماء الريّ المالح يراكم الأملاح في التربة مع الوقت — يلزم غسيل دوري."
            if risk != "none"
            else "ماء مناسب للريّ دون قيود ملوحة تُذكر."
        ),
    }


def leaching_requirement(ecw_dsm: float, crop_threshold_ece: float) -> dict:
    """يحسب احتياج الغسيل (LR): نسبة الماء الإضافي لطرد الأملاح.

    LR = ECw / (5 × ECe_threshold − ECw)   [معادلة FAO المبسّطة]
    حيث ECe_threshold = عتبة تحمّل المحصول لملوحة التربة.
    """
    denom = 5 * crop_threshold_ece - ecw_dsm
    if denom <= 0:
        return {
            "supported": True,
            "feasible": False,
            "message_ar": (
                "ملوحة الماء عالية جدّاً نسبةً لتحمّل المحصول — الغسيل وحده "
                "لا يكفي. غيّر المحصول لأكثر تحمّلاً أو حسّن مصدر الماء."
            ),
        }
    lr = ecw_dsm / denom
    lr_pct = round(lr * 100, 1)
    return {
        "supported": True,
        "feasible": True,
        "leaching_fraction": round(lr, 3),
        "leaching_pct": lr_pct,
        "advice_ar": (
            f"احتياج الغسيل ~{lr_pct}%: أضف هذه النسبة فوق احتياج الريّ العادي "
            "لطرد الأملاح أسفل منطقة الجذور. يتطلّب تصريفاً جيّداً."
        ),
        "yemen_note_ar": (
            "الغسيل يستهلك ماءً إضافيّاً — وازن بين طرد الملح وشحّ المياه. "
            "التصريف الجيّد ضروري وإلّا ترتفع الأملاح ثانيةً."
        ),
        "note_ar": "تقدير FAO مبسّط — التطبيق الفعلي يعتمد على نوع التربة والتصريف.",
    }


def sodium_hazard(sar: float) -> dict:
    """يقيّم خطر الصوديوم (SAR) على بنية التربة ونفاذيّتها."""
    if sar < 10:
        cls, cls_ar = "low", "منخفض"
        effect = "لا خطر صوديوم يُذكر على بنية التربة."
    elif sar < 18:
        cls, cls_ar = "medium", "متوسّط"
        effect = "خطر متوسّط — قد تتأثّر نفاذيّة التربة الطينيّة."
    elif sar < 26:
        cls, cls_ar = "high", "عالٍ"
        effect = "خطر عالٍ — تدهور بنية التربة ونفاذيّتها محتمل."
    else:
        cls, cls_ar = "very_high", "عالٍ جدّاً"
        effect = "خطر شديد — التربة الصودية تفقد بنيتها؛ يلزم جبس وإصلاح."

    return {
        "sar": sar,
        "class": cls,
        "class_ar": cls_ar,
        "effect_ar": effect,
        "remedy_ar": (
            "إضافة الجبس الزراعي (كبريتات الكالسيوم) يزيح الصوديوم ويحسّن البنية."
            if cls in ("high", "very_high")
            else "لا حاجة لإجراء خاصّ حاليّاً، تابع المراقبة."
        ),
    }


def salinity_assessment(
    ece_dsm: float | None = None,
    ecw_dsm: float | None = None,
    sar: float | None = None,
    crop_threshold_ece: float | None = None,
) -> dict:
    """تقييم شامل للملوحة يجمع كلّ المؤشّرات المتاحة في توصية واحدة."""
    out: dict = {"supported": True, "components": {}}
    recommendations: list[str] = []

    if ece_dsm is not None:
        soil = classify_soil_salinity(ece_dsm)
        out["components"]["soil_salinity"] = soil
        if soil["class"] not in ("non_saline", "slightly_saline"):
            recommendations.append(
                f"التربة {soil['class_ar']} — اختر محاصيل متحمّلة (شعير، نخيل) أو طبّق غسيلاً."
            )

    if ecw_dsm is not None:
        water = classify_water_salinity(ecw_dsm)
        out["components"]["water_salinity"] = water
        if water["risk"] != "none":
            recommendations.append(
                f"ماء الريّ {water['risk_ar']} — غسيل دوري + تصريف جيّد لمنع التراكم."
            )

    if ecw_dsm is not None and crop_threshold_ece is not None:
        lr = leaching_requirement(ecw_dsm, crop_threshold_ece)
        out["components"]["leaching"] = lr

    if sar is not None:
        out["components"]["sodium_hazard"] = sodium_hazard(sar)
        if sar >= 18:
            recommendations.append("خطر صوديوم عالٍ — أضف الجبس الزراعي لحماية بنية التربة.")

    if not out["components"]:
        return {"supported": False, "message_ar": "قدّم على الأقلّ ECe (تربة) أو ECw (ماء) أو SAR."}

    out["recommendations_ar"] = recommendations or ["المؤشّرات ضمن الأمان — تابع المراقبة الدوريّة."]
    out["disclaimer_ar"] = (
        "تقييم إرشادي بمعايير FAO. القيم الفعليّة من المختبر، والإدارة تعتمد على "
        "نوع التربة والتصريف المحلّي. توجّه لا يفرض."
    )
    out["yemen_context_ar"] = (
        "الملوحة مشكلة محلّيّة في مناطق محدّدة (بعض الجوف، السهول الساحليّة، "
        "مناطق الريّ الجوفي المكثّف) — لا تعمّم على كلّ اليمن. حيث توجد، يراكم "
        "الريّ المطوّل بمناخ جافّ الأملاح؛ الغسيل يحلّ لكن يستهلك ماءً شحيحاً، "
        "والتصريف الجيّد ضروري."
    )
    return out
