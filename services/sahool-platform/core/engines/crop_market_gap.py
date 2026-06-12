"""core/engines/crop_market_gap.py — كشف تركّز المحاصيل وفجوة السوق الإقليميّة.

الفكرة (مُستلهَمة من مبدأ LULC في المقال — "معرفة ما يُزرع فعلاً في كلّ
منطقة عبر الزمن" — لا من منتجات LULC كأداة): سهول يعرف اتجاه العرض الإجمالي
(regional_supply_signal) لكن **لا يميّز حسب المحصول**. هذا يدمج:
  • تركّز المحاصيل الفعلي (كم حقلاً يزرع X في منطقة Y) = طبقة "الاستخدام"
  • الملاءمة (هل X مناسب للمنطقة؟ من suited_for_zone/high_value_crops)
لكشف: التشبّع (فائض محتمل) والفجوة (فرصة غير مستغلّة).

⚠ المبدأ (صدق صارم، اتّساقاً مع market_analyzer):
  • **حقول المنصّة المشتركة فقط** — لا مسح حقول الآخرين سرّاً (خصوصيّة)
  • **اتجاه نسبي لا رقم مطلق**: "تركّز مرتفع/منخفض" لا "العرض = X طن"
  • **لا تنبّؤ سعر**: التشبّع إشارة ضغط محتمل، لا سعر مستقبلي مفبرك
  • الفرصة = مناسب للمنطقة + قليل الزراعة (لا توصية عمياء)
  • لا اختراع: إن قلّت العيّنة (حقول المنصّة)، يُعلَن نقص الثقة

⚠ ليس LULC حقيقيّاً (لا أقمار صناعيّة لكلّ المنطقة). هو إسقاط مبدأ LULC على
حقول المنصّة المعروفة — عيّنة لا مسح شامل. يُعلَن ذلك صراحةً.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConcentrationLevel(str, Enum):
    HIGH = "high"  # تركّز مرتفع — تشبّع محتمل
    MODERATE = "moderate"
    LOW = "low"  # تركّز منخفض — فرصة محتملة إن كان مناسباً
    NONE = "none"  # لا يُزرع — فجوة كاملة إن كان مناسباً


@dataclass
class CropConcentration:
    """تركّز محصول في منطقة (من حقول المنصّة)."""

    crop_id: str
    zone_key: str
    field_count: int  # كم حقلاً يزرعه (بالمنصّة)
    total_fields_in_zone: int  # إجماليّ حقول المنطقة (بالمنصّة)

    @property
    def share(self) -> float:
        if self.total_fields_in_zone <= 0:
            return 0.0
        return self.field_count / self.total_fields_in_zone


# عتبات التركّز (نسبة حقول المنطقة التي تزرع المحصول)
HIGH_CONCENTRATION = 0.40  # >40% من حقول المنطقة = تشبّع محتمل
LOW_CONCENTRATION = 0.10  # <10% = تركّز منخفض
MIN_SAMPLE_FIELDS = 5  # دون هذا، العيّنة أصغر من أن يُعتمَد عليها


def classify_concentration(conc: CropConcentration) -> ConcentrationLevel:
    """يصنّف مستوى التركّز (حتمي)."""
    if conc.field_count == 0:
        return ConcentrationLevel.NONE
    share = conc.share
    if share >= HIGH_CONCENTRATION:
        return ConcentrationLevel.HIGH
    if share <= LOW_CONCENTRATION:
        return ConcentrationLevel.LOW
    return ConcentrationLevel.MODERATE


def assess_crop_gap(
    conc: CropConcentration,
    is_suited_to_zone: bool,
    market_gap_score: float | None = None,
) -> dict:
    """يقيّم فجوة/تشبّع محصول في منطقة: تشبّع؟ فرصة؟ (يدمج تركّز + ملاءمة).

    market_gap_score: من market_analyzer (فجوة إحلال الواردات) إن توفّر.
    """
    level = classify_concentration(conc)
    low_sample = conc.total_fields_in_zone < MIN_SAMPLE_FIELDS

    # المنطق: تشبّع = تركّز مرتفع؛ فرصة = منخفض/معدوم + مناسب
    if level == ConcentrationLevel.HIGH:
        signal = "saturation"
        signal_ar = (
            f"تركّز مرتفع ({conc.share:.0%} من حقول المنطقة بالمنصّة) — "
            "فائض محتمل وضغط سعري هبوطي. فكّر في تنويع المحاصيل."
        )
    elif level in (ConcentrationLevel.LOW, ConcentrationLevel.NONE) and is_suited_to_zone:
        signal = "opportunity"
        gap_hint = ""
        if market_gap_score is not None and market_gap_score > 0.3:
            gap_hint = " وفجوة إحلال واردات إيجابيّة (المحلّي أرخص)."
        signal_ar = (
            f"تركّز منخفض ({conc.share:.0%}) + مناسب للمنطقة — فرصة محتملة غير مستغلّة.{gap_hint}"
        )
    elif level in (ConcentrationLevel.LOW, ConcentrationLevel.NONE) and not is_suited_to_zone:
        signal = "not_suited"
        signal_ar = "قليل الزراعة لأنّه غير مناسب للمنطقة — ليس فجوة فرصة."
    else:
        signal = "balanced"
        signal_ar = f"تركّز معتدل ({conc.share:.0%}) — سوق متوازن نسبيّاً."

    result = {
        "crop_id": conc.crop_id,
        "zone_key": conc.zone_key,
        "concentration_level": level.value,
        "field_count": conc.field_count,
        "zone_share_pct": round(conc.share * 100, 1),
        "is_suited": is_suited_to_zone,
        "signal": signal,
        "signal_ar": signal_ar,
        "confidence": "low" if low_sample else "moderate",
    }
    if low_sample:
        result["sample_warning_ar"] = (
            f"⚠ عيّنة صغيرة ({conc.total_fields_in_zone} حقل بالمنصّة) — "
            "إشارة استرشاديّة ضعيفة، ليست مسحاً شاملاً للمنطقة."
        )
    return result


def regional_crop_map(
    concentrations: list[CropConcentration],
    suitability: dict[str, bool],
    market_gaps: dict[str, float] | None = None,
) -> dict:
    """خريطة تركّز المحاصيل الإقليميّة: التشبّعات + الفرص (إسقاط مبدأ LULC).

    مُستلهَم من LULC: "ما يُزرع فعلاً" — لكن على حقول المنصّة (عيّنة لا مسح).
    """
    gaps = market_gaps or {}
    assessed = [
        assess_crop_gap(c, suitability.get(c.crop_id, False), gaps.get(c.crop_id))
        for c in concentrations
    ]
    saturated = [a for a in assessed if a["signal"] == "saturation"]
    opportunities = [a for a in assessed if a["signal"] == "opportunity"]

    return {
        "total_crops_analysed": len(assessed),
        "saturated_crops": saturated,
        "opportunity_crops": opportunities,
        "all_assessments": assessed,
        "summary_ar": (
            f"{len(saturated)} محصول متشبّع (فائض محتمل)، "
            f"{len(opportunities)} فرصة محتملة غير مستغلّة"
        ),
        "honesty_note_ar": (
            "إسقاط مبدأ LULC على حقول المنصّة (عيّنة، لا مسح شامل بالأقمار). "
            "اتجاهات نسبيّة لا أرقام مطلقة، ولا تنبّؤ سعر. التشبّع/الفرصة "
            "إشارات استرشاديّة تُدمَج مع خبرة المزارع وبيانات السوق الفعليّة."
        ),
        "privacy_note_ar": (
            "يُحلّل حقول المنصّة المشتركة فقط (احترام الخصوصيّة) — لا مسح سرّي لحقول خارج المنصّة."
        ),
    }
