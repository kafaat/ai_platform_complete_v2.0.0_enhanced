"""
api/soil_sampling_protocol.py — بروتوكول أخذ عيّنة التربة الصحيحة

جانب جديد عملي: المنصّة تحلّل التربة (pH/EC/عناصر) وتبني عليها توصيات، لكن
**نتائج التحليل دقيقة فقط بقدر دقّة العيّنة المأخوذة** — وجمع العيّنة من أكبر
مصادر الخطأ. هذه الوحدة ترشد المزارع لأخذ عيّنة تمثيليّة صحيحة.

المصدر: بروتوكولات علميّة (Oregon State Univ. Extension EC 628، Univ. Idaho
BUL 915، UC Davis) — مبادئ عامّة معتمدة دوليّاً.

المحاور:
  • عدد العيّنات الفرعيّة حسب مساحة الحقل
  • العمق المناسب حسب الغرض/المحصول
  • النمط (W أو متعرّج) + العيّنة المركّبة
  • التوقيت (ومتى لا تأخذ عيّنة)
  • الأدوات والتعامل والشحن

⚠ إرشاد عامّ. اتبع تعليمات مختبرك المحدّد (قد تختلف). توجّه لا يفرض.
السياق اليمني: عيّنة صحيحة = توصية تسميد/ملاءمة صحيحة = توفير مال وتربة.
"""

from __future__ import annotations

from shared.soil_sampling_guidance import COMPOSITE_PURPOSES, PURPOSE_GUIDANCE


def subsamples_for_area(area_ha: float) -> dict:
    """يحسب عدد العيّنات الفرعيّة الموصى بها حسب مساحة الحقل."""
    if area_ha <= 0:
        return {"supported": False, "message_ar": "أدخل مساحة صحيحة بالهكتار."}
    # القاعدة: حقل صغير (<2ha) ~15 عيّنة، كبير (>10ha) ~30. تدرّج خطّي بينهما.
    if area_ha < 2:
        n = 15
    elif area_ha > 10:
        n = 30
    else:
        n = round(15 + (area_ha - 2) / (10 - 2) * (30 - 15))
    return {
        "supported": True,
        "area_ha": area_ha,
        "basis": "planning_heuristic_per_homogeneous_management_unit",
        "subsamples": n,
        "advice_ar": (
            f"اجمع ~{n} جسة من العمق نفسه موزّعة داخل الوحدة المتجانسة، ثمّ اخلطها "
            "في عيّنة مركّبة تمثّل تلك الوحدة."
        ),
        "principle_ar": "كلّما زادت العيّنات الفرعيّة، زادت دقّة تمثيل الحقل.",
        "note_ar": "افصل المناطق المختلفة (منخفضات، تلال متعرّية، أطراف) بعيّنات مستقلّة.",
    }


_LABELS = {
    "fertility": "خصوبة التربة",
    "no_till": "الحقل غير المحروث",
    "nitrate": "نترات التربة",
    "orchard": "البساتين",
    "salinity": "ملوحة التربة",
    "texture": "قوام التربة",
}


def sampling_depth(purpose: str = "general") -> dict:
    """Expose the same purpose-specific guidance as the planner; the lab sets numeric layers."""
    key = purpose.strip().lower()
    if key == "general":
        key = "fertility"
    guidance = PURPOSE_GUIDANCE.get(key)
    return {
        "purpose": purpose,
        "sampling_purpose": key,
        "supported": guidance is not None,
        "depth_status": "requires_lab_protocol" if guidance else "unknown_sampling_purpose",
        "depth_ar": guidance or "غرض غير معروف. اختر غرضاً من القائمة.",
        "applies_to_ar": _LABELS.get(key, ""),
        "principle_ar": "سجّل عمق البداية والنهاية لكل كيس ووحّد الأعماق بين جولات المقارنة.",
        "all_purposes_ar": [
            {"purpose": k, "depth_ar": guidance, "for_ar": _LABELS[k]}
            for k, guidance in PURPOSE_GUIDANCE.items()
        ],
    }


def sampling_protocol(area_ha: float | None = None, purpose: str = "general") -> dict:
    """البروتوكول الكامل لأخذ عيّنة تربة صحيحة (الخطوات + التحذيرات)."""
    depth = sampling_depth(purpose)
    out = {"supported": depth["supported"], "depth": depth}
    if not out["supported"]:
        return out
    composite = depth["sampling_purpose"] in COMPOSITE_PURPOSES
    out["composite"] = composite
    if area_ha is not None:
        if composite:
            out["subsamples"] = subsamples_for_area(area_ha)
        else:
            out["subsamples"] = {
                "supported": False,
                "subsamples": None,
                "message_ar": "حدّد مواضع وطبقات مستقلة حسب غرض التشخيص.",
            }

    out["steps_ar"] = [
        "١. افصل وحدات الإدارة وتاريخ الري والتسميد قبل توزيع المواقع.",
        "٢. جهّز مسباراً وأوعية وأكياساً نظيفة وملصقاً لكل عينة.",
        "٣. أزل البقايا السطحية قبل إدخال المسبار.",
        depth["depth_ar"],
        "٥. اخلط الجسات المتساوية العمق من الوحدة نفسها في عيّنة مركّبة."
        if composite
        else "٥. ضع كل موضع وطبقة في كيس مستقل.",
        "٦. جهّز عيّنة بالحجم وحالة الحفظ المطلوبين من المختبر للتحليل المختار.",
        "٧. سجّل معرف الكيس والموقع الفعلي والعمق والوقت وظروف الري.",
        "٨. اتبع تعليمات المختبر للحفظ والنقل، ونسّق شحن عينات النترات قبل بدء الجولة.",
    ]

    out["avoid_ar"] = [
        "لا تأخذ عيّنة بعد التسميد/الجير/السماد مباشرةً.",
        "لا تأخذ عيّنة والتربة مشبعة بالماء.",
        "تجنّب أطراف الحقل والطرق القديمة ومناطق تغذية الحيوانات (تراكيز شاذّة).",
        "للحديد/الزنك: تجنّب أدوات حديديّة/زنكيّة (تلوّث العيّنة).",
    ]

    out["timing_ar"] = (
        "حدّد توقيت الجولة حسب الغرض ومرحلة المحصول، وسجّل تاريخ آخر ري وتسميد للمقارنة."
    )
    out["yemen_note_ar"] = "في الحقول المروية سجّل مصدر مياه الري وموضع العينة من نظام الري."
    out["disclaimer_ar"] = "اتبع معايرة المختبر المحلي لكل اختبار عند اختيار أعماق الجمع."
    return out
