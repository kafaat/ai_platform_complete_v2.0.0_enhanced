"""api/economic_state.py — الحالة الاقتصاديّة للمحصول (طبقة نقيّة مستقلّة)

#378 في مسار «نظام تشغيل المحصول»: تحسب العائد والتكاليف والهامش المتوقّع من
**أسعار/تكاليف يمرّرها المستدعي** — لا تُلفَّق أرقام اقتصاديّة أبداً.

نقيّة تماماً وحتميّة: **لا I/O، لا ربط بالواجهة، ولا تعديل للقرار الزراعيّ** (ذلك
يأتي لاحقاً في profit_aware_unified_decision). تُنتج فقط الكتلة الاقتصاديّة.

المخرجات (مطابقة لعقد المستخدم): gross_revenue / water_cost / energy_cost /
fertilizer_cost / expected_margin / margin_uncertainty / confidence — مع حقول صدق
(status / missing_inputs / calibrated). أيّ مُدخَل سعريّ غائب ⇒ مكوّنه None والحالة
partial/not_configured (لا صفر مُختلق).
"""

from __future__ import annotations

# عدم يقين الغلّة الافتراضيّ (±) — يهيمن على عدم يقين الهامش (الإيراد أكبر بنود).
# ⚠ تقديريّ، يحتاج معايرة محلّيّة. موسوم calibrated=False.
_DEFAULT_YIELD_UNCERTAINTY = 0.20
# عدم يقين الأسعار الافتراضيّ (±) — أسواق اليمن متقلّبة. تقديريّ.
_DEFAULT_PRICE_UNCERTAINTY = 0.10


def _mul(a: float | None, b: float | None) -> float | None:
    """حاصل ضرب مُدخَلين سعريّين؛ None إن غاب أحدهما (لا اختلاق صفر)."""
    if a is None or b is None:
        return None
    return float(a) * float(b)


def economic_state(
    expected_yield_t_ha: float | None = None,
    crop_price_per_t: float | None = None,
    irrigation_m3_ha: float | None = None,
    water_price_per_m3: float | None = None,
    energy_kwh_ha: float | None = None,
    energy_price_per_kwh: float | None = None,
    fertilizer_kg_ha: float | None = None,
    fertilizer_price_per_kg: float | None = None,
    yield_uncertainty: float = _DEFAULT_YIELD_UNCERTAINTY,
    price_uncertainty: float = _DEFAULT_PRICE_UNCERTAINTY,
) -> dict:
    """يحسب الإيراد/التكاليف/الهامش المتوقّع من أسعار مُمرَّرة — نقيّ حتميّ.

    الإيراد = الغلّة × سعر المحصول. كلّ تكلفة = كمّيّة × سعر وحدتها. الهامش = الإيراد
    − مجموع التكاليف المتوفّرة. عدم يقين الهامش (±) ≈ √((U_yield·revenue)² +
    Σ(U_price·cost)²) — انتشار تقريبيّ شفّاف. الثقة من اكتمال المدخلات.
    صدق: مُدخَل غائب ⇒ مكوّنه None ولا يُحتسب صفراً.
    """
    warnings_ar: list[str] = [
        "أرقام اقتصاديّة من أسعار مُمرَّرة وغلّة متوقّعة غير معايَرة — للإرشاد لا للمحاسبة",
    ]
    missing: list[str] = []

    gross_revenue = _mul(expected_yield_t_ha, crop_price_per_t)
    if gross_revenue is None:
        missing += [
            k
            for k, v in (
                ("expected_yield_t_ha", expected_yield_t_ha),
                ("crop_price_per_t", crop_price_per_t),
            )
            if v is None
        ]

    water_cost = _mul(irrigation_m3_ha, water_price_per_m3)
    if water_cost is None:
        missing += [
            k
            for k, v in (
                ("irrigation_m3_ha", irrigation_m3_ha),
                ("water_price_per_m3", water_price_per_m3),
            )
            if v is None
        ]

    energy_cost = _mul(energy_kwh_ha, energy_price_per_kwh)
    if energy_cost is None:
        missing += [
            k
            for k, v in (
                ("energy_kwh_ha", energy_kwh_ha),
                ("energy_price_per_kwh", energy_price_per_kwh),
            )
            if v is None
        ]

    fertilizer_cost = _mul(fertilizer_kg_ha, fertilizer_price_per_kg)
    if fertilizer_cost is None:
        missing += [
            k
            for k, v in (
                ("fertilizer_kg_ha", fertilizer_kg_ha),
                ("fertilizer_price_per_kg", fertilizer_price_per_kg),
            )
            if v is None
        ]

    cost_components = [c for c in (water_cost, energy_cost, fertilizer_cost) if c is not None]
    total_cost = round(sum(cost_components), 2) if cost_components else None

    expected_margin: float | None = None
    margin_uncertainty: float | None = None
    if gross_revenue is not None:
        expected_margin = round(gross_revenue - (total_cost or 0.0), 2)
        # انتشار عدم اليقين: الإيراد (غلّة×سعر) أكبر بند ⇒ يهيمن.
        rev_var = (yield_uncertainty * gross_revenue) ** 2 + (
            price_uncertainty * gross_revenue
        ) ** 2
        cost_var = sum((price_uncertainty * c) ** 2 for c in cost_components)
        margin_uncertainty = round((rev_var + cost_var) ** 0.5, 2)

    # الثقة من اكتمال الأزواج السعريّة (4 مكوّنات) — كسر بسيط شفّاف، مقصوص.
    components_present = sum(
        x is not None for x in (gross_revenue, water_cost, energy_cost, fertilizer_cost)
    )
    confidence = round(0.25 + 0.15 * components_present, 2)  # 0.25 (لا شيء) → 0.85 (الكلّ)

    if components_present == 0:
        status = "not_configured"
    elif missing:
        status = "partial"
    else:
        status = "ok"

    return {
        "gross_revenue": round(gross_revenue, 2) if gross_revenue is not None else None,
        "water_cost": round(water_cost, 2) if water_cost is not None else None,
        "energy_cost": round(energy_cost, 2) if energy_cost is not None else None,
        "fertilizer_cost": round(fertilizer_cost, 2) if fertilizer_cost is not None else None,
        "total_cost": total_cost,
        "expected_margin": expected_margin,
        "margin_uncertainty": margin_uncertainty,
        "confidence": confidence,
        "status": status,
        "missing_inputs": missing,
        "calibrated": False,
        "warnings_ar": warnings_ar,
    }
