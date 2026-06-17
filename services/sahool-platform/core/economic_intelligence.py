"""core/economic_intelligence.py — ترجمة الأثر إلى قيمة اقتصاديّة (نقيّ، الشريحة 10).

المرحلة C. قياس الأثر (الشريحة 8) يُنتج كمّيّات فيزيائيّة (ماء موفَّر، نسبة نجاح)؛ هذه
الوحدة تترجمها إلى **لغة المزارع: المال**. كم تكلفة ماء تجنّبناها؟ ما قيمة دورة التشغيل؟
تُغذّي واجهة الذكاء الاقتصاديّ بأرقام قابلة للفهم (مطابقة لروح core.farm_ledger: شفّاف،
محايد العملة، لا تنبّؤ أسعار سوق).

نقيّ وحتميّ (لا I/O): يأخذ ملخّص الأثر + معاملات اقتصاديّة (تكلفة الماء/الوحدة، المساحة،
العملة)، يُرجِع `EconomicSummary`. صدق صارم: لا تُحسَب قيمة الماء المُتجنَّبة إلّا حين
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
    water_saved_mm: float
    water_saved_m3: float | None = None  # حجم الماء الموفَّر (إن توفّرت المساحة)
    water_cost_avoided: float | None = None  # قيمة الماء المُتجنَّبة (إن توفّرت التكلفة)
    notes_ar: list[str] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# 1مم على هكتار واحد = 10 م³ ماء (ثابت فيزيائيّ: 1mm × 10,000m² = 10m³).
_MM_HA_TO_M3 = 10.0


def summarize_economics(
    impact: dict,
    *,
    currency: str = "YER",
    area_ha: float | None = None,
    water_cost_per_m3: float | None = None,
) -> EconomicSummary:
    """يترجم ملخّص الأثر إلى ملخّص اقتصاديّ (نقيّ) — انظر docstring الوحدة.

    `impact`: ImpactSummary.to_dict() (يحوي water_saved_mm، executed، success_rate).
    `area_ha`: مساحة الحقل/الحقول (لتحويل المم إلى م³). `water_cost_per_m3`: تكلفة الوحدة.
    صدق: الحجم يُحسَب فقط مع المساحة؛ والقيمة المُتجنَّبة فقط مع التكلفة والحجم — وإلّا None
    + ملاحظة صريحة بالسبب. لا قيمة مُلفَّقة.
    """
    water_saved_mm = float(impact.get("water_saved_mm", 0.0) or 0.0)
    executed = int(impact.get("executed", 0) or 0)
    success_rate = float(impact.get("success_rate", 0.0) or 0.0)
    notes: list[str] = []

    water_saved_m3: float | None = None
    if area_ha is not None and area_ha > 0:
        water_saved_m3 = round(water_saved_mm * area_ha * _MM_HA_TO_M3, 2)
    else:
        notes.append("حجم الماء الموفَّر غير محسوب — لم تُمرَّر المساحة (area_ha).")

    water_cost_avoided: float | None = None
    if water_saved_m3 is not None and water_cost_per_m3 is not None and water_cost_per_m3 >= 0:
        water_cost_avoided = round(water_saved_m3 * water_cost_per_m3, 2)
    elif water_cost_per_m3 is None:
        notes.append("قيمة الماء المُتجنَّبة غير محسوبة — لم تُمرَّر تكلفة الوحدة (water_cost_per_m3).")

    return EconomicSummary(
        currency=currency,
        executed_decisions=executed,
        success_rate=round(success_rate, 3),
        water_saved_mm=round(water_saved_mm, 2),
        water_saved_m3=water_saved_m3,
        water_cost_avoided=water_cost_avoided,
        notes_ar=notes or None,
    )
