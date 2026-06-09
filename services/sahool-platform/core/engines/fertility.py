"""
sahool_core.engines.fertility
==============================
Fertiliser need (difference equation) + organic-matter mineralisation
using the Q10 temperature model (critique fix: not a fixed "4-6 weeks").

Fertiliser:  needed = (crop_requirement - available) / use_efficiency
Mineralisation rate (Q10):
    k = k_ref * Q10 ^ ((T - T_ref) / 10)
    half_life = ln(2) / k

In hot arid regions (~30°C mean), mineralisation is fast (half-life ~days),
BUT high C:N (>30:1) delays release regardless of heat.

Sources:
  - Difference equation for fertiliser: FAO nutrient-balance approach.
  - Q10 mineralisation: standard soil biogeochemistry (Q10~2,
    k_ref~0.05/day at 20°C). C:N delay: Janssen 1996 / standard agronomy.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class FertiliserNeed:
    nutrient: str
    required_kg_ha: float
    available_kg_ha: float
    deficit_kg_ha: float
    fertiliser_kg_ha: float
    note_ar: str


def fertiliser_need(
    nutrient: str,
    required_kg_ha: float,
    available_kg_ha: float,
    use_efficiency: float = 0.5,
) -> FertiliserNeed:
    """Difference equation. Efficiency 0.5 typical for N (urea)."""
    deficit = max(0.0, required_kg_ha - available_kg_ha)
    fert = deficit / max(0.1, use_efficiency)
    if deficit <= 0:
        note = f"{nutrient}: المتوفر كافٍ — لا حاجة للإضافة"
    else:
        note = (f"{nutrient}: نقص {deficit:.0f} كجم/هكتار → "
                f"{fert:.0f} كجم سماد (كفاءة {use_efficiency:.0%})")
    return FertiliserNeed(
        nutrient=nutrient,
        required_kg_ha=required_kg_ha,
        available_kg_ha=available_kg_ha,
        deficit_kg_ha=round(deficit, 1),
        fertiliser_kg_ha=round(fert, 1),
        note_ar=note,
    )


def mineralisation_half_life_days(
    temp_c: float, cn_ratio: float,
    k_ref_per_day: float = 0.05, q10: float = 2.0, t_ref: float = 20.0,
) -> dict:
    """Q10 mineralisation half-life. Accounts for C:N delay."""
    k = k_ref_per_day * (q10 ** ((temp_c - t_ref) / 10.0))
    half_life = math.log(2) / k if k > 0 else float("inf")
    delayed = cn_ratio > 30.0
    if delayed:
        # high C:N immobilises N first -> effective delay 3-6x
        half_life *= 4.0
        note = (f"C:N={cn_ratio:.0f} > 30 → تثبيت مؤقت للنيتروجين، "
                f"المعدنية متأخرة رغم الحرارة")
    else:
        note = f"معدنية سريعة عند {temp_c:.0f}°م (C:N={cn_ratio:.0f})"
    return {
        "k_per_day": round(k, 4),
        "half_life_days": round(half_life, 1),
        "high_cn_delay": delayed,
        "note_ar": note,
    }


def organic_matter_recommendation(
    current_om_pct: float, optimal_om_pct: float, soil_history: str,
) -> dict:
    """Compost need to reach optimal OM. History adjusts the baseline."""
    om = current_om_pct
    if "fallow_3yr" in soil_history:
        om *= 0.7   # degradation
    elif "rotation" in soil_history:
        om *= 1.1   # improvement from rotation
    if om >= optimal_om_pct:
        return {"status": "مثالي", "compost_tons_per_ha": 0.0,
                "note_ar": "صيانة سنوية 2-3 طن/هكتار"}
    deficit = optimal_om_pct - om
    # ~50% OM content in compost, 20 t/ha raises ~1% (rough agronomic factor)
    compost = round(deficit * 20.0, 1)
    return {
        "status": "ناقص",
        "current_om_pct": round(om, 2),
        "compost_tons_per_ha": compost,
        "note_ar": f"أضف ~{compost} طن/هكتار كومبوست قبل الزراعة 4-6 أسابيع "
                   f"(عدّل حسب C:N والحرارة)",
    }
