"""
sahool_core.district_baseline
==============================
التعلّم الجماعي المتدرّج عبر طيف نضج المزارعين.

المشكلة (واقع الانتشار على شريحة كبيرة):
  مزارعون واعون → فحوصات كاملة → بيانات دقيقة
  مزارعون بسطاء → لا فحوصات → BLOCKED، في الظلام

الفكرة: المزارعون الواعون في مديرية يبنون "خطاً أساسياً" (baseline)،
  والمزارع البسيط يحصل على *سياق مديريته* كـ prior — لا قيمة حقله المزعومة.

المبدأ الحاسم (الصدق):
  ✅ "متوسط ملوحة مديريتك 4.2 (من 6 مزارع محلّلة)" → سياق صادق
  ❌ "ملوحة حقلك 4.2" → كذب، لم نقس حقله

  السياق يوجّه ويحفّز؛ حقل المزارع البسيط يبقى BLOCKED للتوصيات الدقيقة
  حتى يُقاس فعلاً. البيانات الجماعية ترفع الجميع دون اختراع قيم فردية.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median, pstdev

# عتبة الثقة في الخط الأساسي (نفس منطق المعايرة)
MIN_FARMS_FOR_BASELINE = 5


@dataclass
class DistrictBaseline:
    """خط أساسي لمديرية من المزارعين الواعين — سياق لا حقيقة فردية."""

    district_id: str
    observable_id: str  # S3 (ملوحة)، S4 (pH)...
    n_farms: int  # عدد المزارع المُسهِمة (محلّلة فعلاً)
    median_value: float | None
    mean_value: float | None
    spread: float | None  # الانحراف المعياري (تجانس المديرية)
    confidence: str  # none / low / medium
    is_usable: bool  # هل يكفي لسياق موثوق؟
    note_ar: str = ""


def compute_district_baseline(
    district_id: str,
    observable_id: str,
    analyzed_values: list[float],
) -> DistrictBaseline:
    """يبني خطاً أساسياً من قيم المزارع المُحلَّلة فعلياً في المديرية.
    analyzed_values: قيم مخبرية حقيقية فقط (لا تقديرات)."""
    n = len(analyzed_values)
    if n == 0:
        return DistrictBaseline(
            district_id,
            observable_id,
            0,
            None,
            None,
            None,
            "none",
            False,
            "لا مزارع محلّلة في هذه المديرية بعد",
        )
    med = round(median(analyzed_values), 2)
    avg = round(mean(analyzed_values), 2)
    spread = round(pstdev(analyzed_values), 2) if n > 1 else None

    if n < MIN_FARMS_FOR_BASELINE:
        conf, usable = "low", False
        note = f"{n} مزارع محلّلة فقط (<{MIN_FARMS_FOR_BASELINE}) — سياق أولي غير موثوق للتعميم"
    else:
        # التجانس يحدّد الثقة: تشتّت عالٍ = مديرية غير متجانسة
        conf = "medium" if (spread is None or spread < med * 0.3) else "low"
        usable = True
        note = (
            f"خط أساسي من {n} مزارع محلّلة. "
            f"{'متجانس' if conf == 'medium' else 'متفاوت — استخدم بحذر'}"
        )
    return DistrictBaseline(district_id, observable_id, n, med, avg, spread, conf, usable, note)


@dataclass
class FarmerContext:
    """ما يُعرض للمزارع البسيط: سياق مديريته، لا قيمة حقله."""

    headline_ar: str
    context_ar: str
    is_field_specific: bool  # دائماً False — سياق لا قيمة حقل
    motivation_ar: str  # تحفيز للفحص
    blocks_precise: bool = True  # حقله يبقى BLOCKED للدقيق


def context_for_low_data_farmer(
    baseline: DistrictBaseline,
    observable_name_ar: str,
) -> FarmerContext:
    """يحوّل خط أساس المديرية لسياق محفّز للمزارع البسيط.
    لا يدّعي أبداً معرفة قيمة حقله — يعرض سياق جيرانه فقط."""
    if not baseline.is_usable:
        return FarmerContext(
            headline_ar=f"{observable_name_ar}: لا سياق كافٍ بعد",
            context_ar=(
                f"مديريتك تحتاج {MIN_FARMS_FOR_BASELINE} مزارع محلّلة "
                f"على الأقل (الحالي: {baseline.n_farms})"
            ),
            is_field_specific=False,
            motivation_ar="كن أوّل من يحلّل تربته في مديريتك — تساعد جيرانك أيضاً",
        )
    return FarmerContext(
        headline_ar=f"سياق {observable_name_ar} في مديريتك",
        context_ar=(
            f"متوسط {observable_name_ar} لدى {baseline.n_farms} مزارع "
            f"محلّلة في مديريتك ≈ {baseline.median_value}. "
            f"هذا سياق المنطقة، وليس قيمة حقلك."
        ),
        is_field_specific=False,  # حاسم: ليس قيمة حقله
        motivation_ar=(
            "حلّل تربتك لتعرف قيمتك الفعلية وتحصل على توصيات دقيقة — قد يختلف حقلك عن المتوسط"
        ),
        blocks_precise=True,  # حقله يبقى محجوباً للتوصيات الدقيقة
    )
