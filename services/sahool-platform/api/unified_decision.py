"""api/unified_decision.py — قرار المحصول الموحّد (Unified Crop Decision)

نواة «منصّة القرار المتمحورة حول المحصول»: تجمع الحالات المحسوبة مسبقاً في **قرار
واحد** بدل قرار ريّ منفصل عن تسميد منفصل عن مخاطر:

  unified_decision = حالة المحصول (crop_twin) + قرار الريّ (irrigation_plan)
                     + قرار التسميد (من حالة العنصر) + المخاطر + الثقة.

طبقة **تركيب نقيّة** (لا I/O، لا محرّك جديد): تتلقّى نواتج الوحدات القائمة وتؤلّفها.
الاقتصاد **مؤجَّل** لطبقة مستقلّة — نحجز له مكاناً صريحاً (not_configured) لا نختلقه.

صدق: تنتقل أوسمة عدم المعايرة/الثقة كما هي؛ ما لا تحمله المدخلات (حرارة/ملوحة)
يُعلَن «يحتاج بيانات» لا يُفبرَك.
"""

from __future__ import annotations

# المدخلات الاقتصاديّة المطلوبة لاحقاً (طبقة economic_state مستقلّة).
_ECONOMIC_REQUIRED_INPUTS = ["crop_price", "water_cost", "energy_cost", "fertilizer_cost"]


def _water_risk(stress_days: int) -> str:
    return "منخفض" if stress_days == 0 else "متوسط" if stress_days <= 2 else "مرتفع"


def unified_decision(crop_twin: dict, irrigation_plan: dict, quality: dict) -> dict:
    """يؤلّف قراراً موحّداً من حالات محسوبة مسبقاً — نقيّ حتميّ.

    crop_twin: ناتج crop_twin_state. irrigation_plan: ناتج plan_irrigation.to_dict.
    quality: ناتج assess_data_quality. لا يعيد الحساب — يجمع ويصوغ التوصية.
    """
    pheno = crop_twin.get("phenology", {})
    water = crop_twin.get("water", {})
    nut = crop_twin.get("nutrient", {})
    plan = irrigation_plan

    # ── قرار الريّ (من الخطّة) ──
    next_irrig = next((d for d in plan.get("days", []) if d.get("irrigation_mm", 0) > 0), None)
    stress_days = len(plan.get("stress_days", []))
    irrigation = {
        "policy": plan.get("policy"),
        "total_mm": plan.get("total_irrigation_mm", 0.0),
        "n_events": plan.get("n_events", 0),
        "next_event_day": next_irrig.get("day_index") if next_irrig else None,
        "next_event_mm": round(next_irrig.get("irrigation_mm", 0.0), 2) if next_irrig else 0.0,
        "stress_days": stress_days,
        "action_ar": (
            f"ريّ {next_irrig['irrigation_mm']:.0f} مم يوم {next_irrig['day_index'] + 1}"
            if next_irrig
            else "لا ريّ مستحقّ خلال الأفق"
        ),
    }

    # ── قرار التسميد (من حالة العنصر) ──
    target = nut.get("target_uptake_kg_ha", 0.0) or 0.0
    to_date = nut.get("uptake_to_date_kg_ha", 0.0) or 0.0
    remaining = max(0.0, target - to_date)
    fert_due = target > 0 and remaining > 0
    fertilization = {
        "stage": nut.get("stage"),
        "uptake_to_date_kg_ha": to_date,
        "remaining_need_kg_ha": round(remaining, 2),
        "due": fert_due,
        "action_ar": (
            f"احتياج متبقٍّ ~{remaining:.0f} كجم/هكتار (مرحلة {nut.get('stage') or '—'})"
            if fert_due
            else ("لا هدف امتصاص مُدخَل" if target <= 0 else "اكتمل الامتصاص المستهدف")
        ),
    }

    # ── المخاطر (الحقيقيّ منها فقط؛ الباقي «يحتاج بيانات») ──
    risks = [
        {"key": "water", "label_ar": "مائي", "level_ar": _water_risk(stress_days)},
        {"key": "heat", "label_ar": "حراريّ", "level_ar": "يحتاج بيانات"},
        {"key": "salinity", "label_ar": "ملوحة", "level_ar": "يحتاج بيانات"},
    ]

    # ── أعلام موحّدة ──
    flags: list[dict] = []
    if water.get("needs_irrigation"):
        flags.append({"code": "water_deficit", "label_ar": "عجز مائيّ — الريّ مستحقّ"})
    if pheno.get("past_maturity"):
        flags.append({"code": "past_maturity", "label_ar": "تجاوز النضج المتوقّع"})
    if fert_due:
        flags.append({"code": "fertilization_due", "label_ar": "تسميد مستحقّ"})

    return {
        "crop": crop_twin.get("crop"),
        "crop_known": crop_twin.get("crop_known", False),
        "phenology": pheno,
        "water_state": water,
        "nutrient_state": nut,
        "irrigation": irrigation,
        "fertilization": fertilization,
        "risks": risks,
        "stress_flags": flags,
        "confidence": quality.get("confidence"),
        "data_quality": quality.get("data_quality"),
        "assumptions": quality.get("assumptions", []),
        "assumptions_ar": quality.get("assumptions_ar", []),
        # الاقتصاد مؤجَّل لطبقة مستقلّة — محجوز صراحةً، لا مُختلق.
        "economic_state": {
            "status": "not_configured",
            "required_inputs": list(_ECONOMIC_REQUIRED_INPUTS),
        },
        "calibrated": False,
        "warnings_ar": list(crop_twin.get("warnings_ar", [])) + list(plan.get("notes_ar", [])),
    }
