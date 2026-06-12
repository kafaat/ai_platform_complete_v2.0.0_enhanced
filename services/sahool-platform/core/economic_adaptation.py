"""core/economic_adaptation.py — تكييف التوصية حسب القدرة الاقتصاديّة للمزارع.

الفجوة المُعالَجة: economic_tier يحوكم (يرفض ما يتجاوز القدرة) لكن لا **يكيّف**
التوصية. صغير الحوزة محدود الدخل يتلقّى نفس توصية المزارع التجاري — قد تكون
خارج قدرته. هذه الطبقة تُقدّم **بدائل متدرّجة حسب القدرة** (لا تمييز سلبي).

⚠ المبدأ (اتّساقاً مع farmer_agency):
  • التكييف **اقتراح لا فرض** — يعرض البديل الأنسب للقدرة + يُبقي الخيار للمزارع
  • لا "deskilling": يشرح *لماذا* البديل أنسب، لا يُخفي الخيار الأعلى
  • حتمي بالكامل (قواعد قدرة مالية) — لا تعلّم من نتائج غائبة، لا اختراع
  • لا يَصِم: "محدود الموارد" وصف للقدرة الحاليّة، لا حكم على المزارع

⚠ ليس تعلّماً آليّاً: لا يوجد بيانات نتائج كافية للتعلّم (feedback_closure مؤجّل).
هذه قواعد تكييف صريحة موثّقة، تتحسّن يدويّاً، لا نموذج يتعلّم من فراغ.

المصدر: مبدأ الزراعة الشاملة (smallholder-inclusive) + farmer_agency +
economic_tier الحالي (نسبة الاستثمار ≤30% من الدخل).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CapacityTier(str, Enum):
    """طبقة القدرة الاقتصاديّة — وصف للقدرة الحاليّة لا حكم على المزارع."""

    SMALLHOLDER = "smallholder"  # صغير الحوزة، موارد محدودة
    MID = "mid"  # متوسّط
    COMMERCIAL = "commercial"  # تجاري، قدرة استثماريّة أوسع


@dataclass(frozen=True)
class CapacityProfile:
    tier: CapacityTier
    label_ar: str
    typical_area_ha: str
    investment_posture_ar: str  # موقف الاستثمار المناسب
    priority_ar: str  # الأولويّة الاقتصاديّة


CAPACITY_PROFILES: dict[CapacityTier, CapacityProfile] = {
    CapacityTier.SMALLHOLDER: CapacityProfile(
        CapacityTier.SMALLHOLDER,
        "صغير الحوزة (موارد محدودة)",
        "< 2 هكتار",
        "تجنّب الاستثمار الكبير المسبق؛ ابدأ بأقلّ تكلفة + عائد سريع",
        "الأمن الغذائي + دخل نقدي سريع منخفض المخاطرة",
    ),
    CapacityTier.MID: CapacityProfile(
        CapacityTier.MID,
        "متوسّط الحوزة",
        "2 – 10 هكتار",
        "استثمار متدرّج؛ وازن بين الأمن الغذائي والمحاصيل النقديّة",
        "توازن الدخل والاستقرار + توسّع حذر",
    ),
    CapacityTier.COMMERCIAL: CapacityProfile(
        CapacityTier.COMMERCIAL,
        "تجاري",
        "> 10 هكتار",
        "استثمار أوسع ممكن؛ محاصيل عالية القيمة/تصدير مع إدارة مخاطر",
        "تعظيم العائد + الوصول للأسواق المتخصّصة",
    ),
}


def infer_capacity_tier(
    area_ha: float | None, annual_revenue_usd: float | None = None
) -> CapacityTier:
    """يستنتج طبقة القدرة من المساحة (+الدخل إن توفّر). حتمي، شفّاف.

    صدق: استدلال تقريبي من المساحة (المؤشّر الأكثر توفّراً). الدخل يحسّنه إن وُجد.
    لا يُخزّن حكماً دائماً — وصف للحالة الحاليّة قابل للتغيّر.
    """
    # الدخل أدقّ إن توفّر
    if annual_revenue_usd is not None:
        if annual_revenue_usd < 2000:
            return CapacityTier.SMALLHOLDER
        if annual_revenue_usd < 20000:
            return CapacityTier.MID
        return CapacityTier.COMMERCIAL
    # وإلّا المساحة
    if area_ha is None:
        return CapacityTier.SMALLHOLDER  # افتراض حذر (الأكثر شيوعاً + الأقلّ مخاطرة)
    if area_ha < 2:
        return CapacityTier.SMALLHOLDER
    if area_ha <= 10:
        return CapacityTier.MID
    return CapacityTier.COMMERCIAL


def adapt_recommendation(
    crop_options: list[dict],
    area_ha: float | None = None,
    annual_revenue_usd: float | None = None,
) -> dict:
    """يكيّف خيارات المحاصيل حسب القدرة — اقتراح متدرّج لا فرض.

    Args:
        crop_options: خيارات محاصيل، كلّ منها dict فيه (اختياريّاً)
                      'upfront_cost_level' (low/mid/high) و'name_ar'.
        area_ha, annual_revenue_usd: لاستنتاج الطبقة.

    Returns: التوصية مكيّفة + شرح + الخيار الكامل محفوظ (لا إخفاء — farmer_agency).
    """
    tier = infer_capacity_tier(area_ha, annual_revenue_usd)
    profile = CAPACITY_PROFILES[tier]

    # ترتيب الخيارات حسب ملاءمة القدرة (لا حذف — ترتيب فقط)
    cost_rank = {"low": 0, "mid": 1, "high": 2}
    if tier == CapacityTier.SMALLHOLDER:
        # صغير الحوزة: الأقلّ تكلفة أوّلاً
        ordered = sorted(
            crop_options, key=lambda c: cost_rank.get(c.get("upfront_cost_level", "mid"), 1)
        )
        fit_note = "رُتّبت بالأقلّ تكلفة أوّلاً (يناسب البدء بموارد محدودة)"
    elif tier == CapacityTier.COMMERCIAL:
        # تجاري: الأعلى استثماراً أوّلاً (القدرة تتيح خيارات أكثر كلفةً مقدّماً).
        # ملاحظة صدق: الترتيب حسب مستوى الاستثمار (upfront_cost_level) لا العائد —
        # لا نملك بيانات عائد هنا، فلا نَعِد به.
        ordered = sorted(
            crop_options, key=lambda c: -cost_rank.get(c.get("upfront_cost_level", "mid"), 1)
        )
        fit_note = "رُتّبت بالأعلى استثماراً أوّلاً (القدرة تتيح خيارات أكثر كلفةً مقدّماً)"
    else:
        ordered = list(crop_options)
        fit_note = "خيارات متوازنة (متوسّط الحوزة)"

    return {
        "display_only": False,  # هذه توصية فعليّة (لا مجرّد عرض)
        "used_in_decision_engine": True,
        "capacity_tier": tier.value,
        "capacity_label_ar": profile.label_ar,
        "investment_posture_ar": profile.investment_posture_ar,
        "economic_priority_ar": profile.priority_ar,
        "adapted_options": ordered,
        "fit_note_ar": fit_note,
        "all_options_visible": True,  # farmer_agency: لا إخفاء للخيار الأعلى
        "agency_note_ar": (
            "هذا ترتيب مقترح حسب قدرتك التقديريّة — وليس حصراً. كلّ الخيارات "
            "معروضة؛ لك أن تختار ما يناسب رؤيتك. إن رأيت الترتيب غير مناسب، "
            "فقد تكون قدرتك أو أولويّتك مختلفة — والقرار قرارك."
        ),
        "disclaimer_ar": (
            "تكييف اقتصادي تقديري (من المساحة/الدخل). لا يَصِم ولا يَحصُر — "
            "يساعد على ملاءمة التوصية للموارد. التكلفة الفعليّة تختلف بالسوق المحلّي."
        ),
    }


def get_capacity_profiles() -> dict:
    """ملفّات طبقات القدرة (مرجع شفّاف)."""
    return {
        "tiers": [
            {
                "tier": p.tier.value,
                "label_ar": p.label_ar,
                "typical_area_ha": p.typical_area_ha,
                "investment_posture_ar": p.investment_posture_ar,
                "priority_ar": p.priority_ar,
            }
            for p in CAPACITY_PROFILES.values()
        ],
        "principle_ar": (
            "التكييف يلائم التوصية للقدرة دون وصم أو حصر. متّسق مع استقلاليّة "
            "المزارع: اقتراح لا فرض، وكلّ الخيارات تبقى مرئيّة."
        ),
    }
