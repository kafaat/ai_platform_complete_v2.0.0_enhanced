"""
sahool_core.engines.supplemental_irrigation
============================================
الري التكميلي للزراعة المطرية — الفجوة الأهمّ لمرتفعات اليمن.

السياق (مراجعة 2026-05-27): محرّك deficit_irrigation يخصّ المناطق
المرويّة (إدارة عجز الريّ). لكن **70% من زراعة اليمن مدرّجة مطرية**
(تعز، إب، ذمار) — تعتمد على المطر، وتحتاج إدارة مختلفة جذرياً:
لا "كم نخفّض الريّ؟" بل "متى وكم نضيف ريّاً تكميلياً عند نقص المطر؟".

المبدأ الفيزيائي:
  الفجوة المائية = ETc (احتياج المحصول) − Rainfall (المطر الفعلي)
  إن > 0 → نقص ماء، فجوة موجبة
  الريّ التكميلي = ملء جزئي للفجوة في المراحل الحرجة فقط

دلالة إيكاردا (مؤكَّدة بحثياً): الريّ التكميلي في المناطق المطرية
يرفع الإنتاجية معتبراً (الأرقام تختلف بالسياق — لذا لا نلصقها رقماً).

الفلسفة (تختلف عن deficit_irrigation):
  • deficit_irrigation: المرويّ يُخفّض الريّ من 100% ETc إلى 60-90%.
  • supplemental_irrigation: المطري يُكمّل من 0% (مطر فقط) باتجاه ETc.
  • النقطة المشتركة: لا نطمح للريّ الكامل — نطمح للكفاءة.

حسّاسية المرحلة (Stage-specific): الريّ التكميلي يُعطى في المراحل
الحرجة (الإزهار، امتلاء الحبّ). الإجهاد المائي عند الإزهار يخفض
الغلّة كارثياً (يُربط بـ planting_window).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# نقاط الحساسية حسب مرحلة النمو (Ky القياسية، FAO-33)
# عالٍ = خفض كبير في الغلّة عند الإجهاد
_STAGE_SENSITIVITY = {
    "germination": 0.40,  # الإنبات: حسّاس متوسط
    "vegetative": 0.55,  # الخضري: تحمّل أفضل
    "flowering": 1.10,  # الإزهار: الأكثر حساسية ← أولوية الريّ التكميلي
    "grain_fill": 0.85,  # امتلاء الحبّ: حسّاس عالٍ
    "maturity": 0.30,  # النضج: لا يحتاج ريّاً
}


@dataclass
class WaterGap:
    etc_mm: float  # احتياج المحصول
    rainfall_mm: float  # المطر الفعلي
    gap_mm: float  # الفجوة (ETc - Rainfall)
    gap_pct: float  # % من احتياج المحصول
    stage: str
    stage_sensitivity: float
    needs_supplemental: bool
    recommended_mm: float | None  # كمية الريّ التكميلي المقترحة
    confidence: str
    warnings_ar: list[str] = field(default_factory=list)
    note_ar: str = ""


def compute_water_gap(
    *,
    etc_mm: float,
    rainfall_mm: float,
    growth_stage: str,
    soil_water_storage_mm: float | None = None,
) -> WaterGap:
    """يحسب فجوة الماء ويوصي بالريّ التكميلي عند الحاجة.

    لا يستبدل الريّ الكامل — يكمّل المطر عند نقصه في المراحل الحرجة.
    soil_water_storage_mm (اختياري): مخزون التربة من المطر السابق — يقلّل الفجوة."""
    warnings: list[str] = []

    if etc_mm <= 0:
        return WaterGap(
            etc_mm,
            rainfall_mm,
            0.0,
            0.0,
            growth_stage,
            0.0,
            False,
            None,
            "none",
            warnings_ar=["ETc غير صالح — لا تقدير ممكن"],
        )

    # حسّاسية المرحلة
    sensitivity = _STAGE_SENSITIVITY.get(growth_stage.lower(), 0.55)
    is_critical_stage = sensitivity >= 0.85  # الإزهار وامتلاء الحبّ

    # المياه المتاحة فعلياً = المطر + المخزون
    available = rainfall_mm + (soil_water_storage_mm or 0.0)
    gap = etc_mm - available
    gap_pct = (gap / etc_mm) * 100

    needs = False
    recommended = None
    confidence = "medium"  # تقديري بطبيعته (المطر متوقّع جزئياً)

    if gap <= 0:
        note = f"المطر ({rainfall_mm}مم) يلبّي الاحتياج ({etc_mm}مم) — لا حاجة لريّ تكميلي"
    elif gap_pct < 20:
        note = f"فجوة طفيفة ({gap_pct:.0f}%) — يمكن تجاوزها بمخزون التربة دون ريّ تكميلي"
    elif is_critical_stage:
        # المرحلة الحرجة + فجوة معتبرة → ريّ تكميلي ضروري
        needs = True
        # توصية محافظة: لا نلبّي الفجوة كاملةً (تجنّب الإفراط)، بل ~70%
        # هذا يحافظ على روح "العجز المُدار" — لا ريّ كامل
        recommended = round(gap * 0.7, 1)
        note = (
            f"مرحلة حرجة ({growth_stage}) + فجوة {gap_pct:.0f}% — "
            f"يوصى بريّ تكميلي ~{recommended}مم (ملء جزئي للفجوة)"
        )
    elif gap_pct < 40:
        # فجوة في مرحلة غير حرجة → اختياري
        note = (
            f"فجوة معتبرة ({gap_pct:.0f}%) لكن مرحلة {growth_stage} "
            "أقلّ حساسية — الريّ التكميلي اختياري"
        )
    else:
        # فجوة كبيرة في مرحلة غير حرجة → ريّ تكميلي مع تحفّظ
        needs = True
        recommended = round(gap * 0.5, 1)
        note = (
            f"فجوة كبيرة ({gap_pct:.0f}%) — ريّ تكميلي محدود ~{recommended}مم "
            "حتى لو المرحلة أقلّ حساسية"
        )

    warnings.append("تقديري — المطر متوقّع، الكفاءة تتأثّر بالتربة والريّ")
    if rainfall_mm == 0:
        warnings.append("لا مطر مسجّل — تحقّق من بيانات محطة الطقس")

    return WaterGap(
        etc_mm=etc_mm,
        rainfall_mm=rainfall_mm,
        gap_mm=round(gap, 1),
        gap_pct=round(gap_pct, 1),
        stage=growth_stage,
        stage_sensitivity=sensitivity,
        needs_supplemental=needs,
        recommended_mm=recommended,
        confidence=confidence,
        warnings_ar=warnings,
        note_ar=note,
    )


def seasonal_summary(monthly_gaps: list[WaterGap]) -> dict:
    """تجميع موسمي: كم شهراً يحتاج ريّاً تكميلياً، إجمالي الفجوة."""
    total_gap = sum(max(0, g.gap_mm) for g in monthly_gaps)
    months_needing = sum(1 for g in monthly_gaps if g.needs_supplemental)
    total_supplemental = sum(g.recommended_mm or 0 for g in monthly_gaps)
    return {
        "total_seasonal_gap_mm": round(total_gap, 1),
        "months_needing_supplemental": months_needing,
        "total_supplemental_recommended_mm": round(total_supplemental, 1),
        "note_ar": (
            f"الموسم: فجوة إجمالية {total_gap:.0f}مم؛ "
            f"{months_needing} شهراً يحتاج تكميلاً؛ "
            f"إجمالي مقترح {total_supplemental:.0f}مم"
        ),
    }
