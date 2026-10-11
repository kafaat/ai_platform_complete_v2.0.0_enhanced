"""core/economic_intelligence.py — ترجمة الأثر إلى قيمة اقتصاديّة (نقيّ، الشريحة 10).

المرحلة C. قياس الأثر (الشريحة 8) يُنتج كمّيّات فيزيائيّة (فرق المطلوب عن المُنفَّذ، نسبة نجاح)؛ هذه
الوحدة تُسعِّر فرقَ المطلوب عن المُنفَّذ — قيمةً اسميّة **لا** تكلفةً تجنّبناها: لا خطّ أساس ولا مقارنة.
تُغذّي واجهة الذكاء الاقتصاديّ بأرقام قابلة للفهم (مطابقة لروح core.farm_ledger: شفّاف،
محايد العملة، لا تنبّؤ أسعار سوق).

نقيّ وحتميّ (لا I/O): يأخذ ملخّص الأثر + معاملات اقتصاديّة (تكلفة الماء/الوحدة، المساحة،
العملة)، يُرجِع `EconomicSummary`. صدق صارم: لا تُحسَب قيمة الفرق إلّا حين
تتوفّر تكلفة الوحدة والمساحة (وإلّا None صراحةً + ملاحظة) — لا اختلاق قيمة بلا مدخلات.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class EconomicSummary:
    """ملخّص اقتصاديّ مُترجَم من الأثر — أرقام قابلة للفهم بالعملة المحدّدة."""

    currency: str
    executed_decisions: int
    success_rate: float
    # REQUESTED-MINUS-APPLIED-REPORTED-AS-WATER-SAVED-01: كان «ماءً موفَّراً» و«تكلفةً متجنَّبة». الفرقُ
    # بين المطلوب والمُنفَّذ مُسعَّراً **ليس** تكلفةً تجنّبناها: لا خطَّ أساس ولا مقارنة ولا قياسَ سحب.
    requested_minus_applied_mm: float
    requested_minus_applied_m3: float | None = None  # حجمُ الفرق (إن توفّرت مساحةُ حقلٍ واحد)
    requested_minus_applied_value: float | None = None  # الفرق × سعر الوحدة — قيمةٌ اسميّة لا وفر
    notes_ar: list[str] | None = None

    def to_dict(self) -> dict:
        from core.impact_measurement import SAVINGS_CLAIM

        return {**asdict(self), "savings_claim": dict(SAVINGS_CLAIM)}


# 1مم على هكتار واحد = 10 م³ ماء (ثابت فيزيائيّ: 1mm × 10,000m² = 10m³).
_MM_HA_TO_M3 = 10.0


def summarize_economics(
    impact: dict,
    *,
    currency: str = "YER",
    area_ha: float | None = None,
    water_cost_per_m3: float | None = None,
    single_field: bool = True,
) -> EconomicSummary:
    """يترجم ملخّص الأثر إلى ملخّص اقتصاديّ (نقيّ) — انظر docstring الوحدة.

    `impact`: ImpactSummary.to_dict() (يحوي requested_minus_applied_mm، executed، success_rate).
    `area_ha`: مساحة الحقل/الحقول (لتحويل المم إلى م³). `water_cost_per_m3`: تكلفة الوحدة.
    صدق: الحجم يُحسَب فقط مع المساحة؛ وقيمة الفرق فقط مع التكلفة والحجم — وإلّا None
    + ملاحظة صريحة بالسبب. لا قيمة مُلفَّقة.
    """
    gap_mm = float(impact.get("requested_minus_applied_mm", 0.0) or 0.0)
    executed = int(impact.get("executed", 0) or 0)
    success_rate = float(impact.get("success_rate", 0.0) or 0.0)
    notes: list[str] = []

    gap_m3: float | None = None
    if area_ha is not None and area_ha > 0 and single_field:
        gap_m3 = round(gap_mm * area_ha * _MM_HA_TO_M3, 2)
    elif area_ha is not None and area_ha > 0:
        # مم مجموعةٌ عبر حقول ⇒ لا تُضرب في مساحةٍ واحدة (غير متّسقة الأبعاد).
        notes.append("حجم الفرق غير محسوب — المليمترات مجموعةٌ عبر حقول ولا تُضرب في مساحة واحدة.")
    else:
        notes.append("حجم الفرق غير محسوب — لم تُمرَّر المساحة (area_ha).")

    gap_value: float | None = None
    if gap_m3 is not None and water_cost_per_m3 is not None and water_cost_per_m3 >= 0:
        gap_value = round(gap_m3 * water_cost_per_m3, 2)
    elif water_cost_per_m3 is None:
        notes.append("قيمة الفرق غير محسوبة — لم تُمرَّر تكلفة الوحدة (water_cost_per_m3).")
    notes.append("الفرقُ بين المطلوب والمُنفَّذ ليس وفراً مثبتاً ولا تكلفةً متجنَّبة (savings_claim).")

    return EconomicSummary(
        currency=currency,
        executed_decisions=executed,
        success_rate=round(success_rate, 3),
        requested_minus_applied_mm=round(gap_mm, 2),
        requested_minus_applied_m3=gap_m3,
        requested_minus_applied_value=gap_value,
        notes_ar=notes or None,
    )
