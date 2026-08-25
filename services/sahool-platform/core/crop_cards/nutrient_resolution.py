"""حلّ الطلب الغذائيّ المرحليّ: بطاقة محايدة الموقع × معايرة إقليميّة بطبقتين.

نفس نمط حلّ سياسات الجذور المدموج في `crop_root_policies` (الخصوصيّة تسبق كلّ
شيء): مدخلة (منطقة، محصول، صنف) المصادَقة > مدخلة (منطقة، محصول، '') المصادَقة
> بطاقة المحصول وحدها. فاشل-مغلق من ثلاث جهات:

· بطاقة بلا منحنيات ⇒ ``blocked`` — لا اختلاق كسور.
· مدخلة معايرة ``uncalibrated`` **لا تُطبَّق أبداً** (خاملة بالعقد، معاملاتها
  1.0 يفرضها المدقّق) — وجودها إعلان بنية لا ترخيص أرقام.
· ``locally_calibrated`` لا تكون ``True`` إلا حين تُطبَّق مدخلة ``validated``
  فعلاً — البطاقة وحدها علمٌ عامّ مقرَّب (``approximation: true``) لا معايرة
  محلّيّة، والتمييز بينهما هو جوهر هذه الطبقة.

المعاملات موسميّة لكلّ عنصر وتُحمَل للمستهلك المطلق (الذي يملك الكمّيّات) —
**لا** تُضرَب في الكسور المرحليّة: الكسور توزيع زمنيّ مجموعه 1.00 لكلّ عنصر،
وضربها بمعامل يكسر جمعها ويخلط «كم» بـ«متى».
"""

from __future__ import annotations

from typing import Any

from core.crop_cards.loader import load_crop_card, stage_nutrient_demand
from core.districts.loader import load_district, validate_district


def _calibration_entries(district_card: dict | None) -> list[dict]:
    if not isinstance(district_card, dict):
        return []
    entries = district_card.get("nutrient_calibration")
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def _pick_tier(entries: list[dict], crop: str, variety: str) -> tuple[dict | None, str]:
    """الطبقتان بترتيب الخصوصيّة — مدخلات ``validated`` وحدها مؤهَّلة."""
    validated = [e for e in entries if e.get("status") == "validated" and e.get("crop") == crop]
    if variety:
        for e in validated:
            if e.get("variety") == variety:
                return e, "district_variety"
    for e in validated:
        if e.get("variety") == "":
            return e, "district_generic"
    return None, "card_baseline"


def resolve_stage_nutrient_demand(
    crop: str,
    *,
    district_id: str | None = None,
    variety: str | None = None,
) -> dict[str, Any]:
    """يحلّ التوزيع المرحليّ + معاملات المعايرة الإقليميّة إن وُجدت مصادَقةً.

    الناتج يحمل دائماً: الطبقة المختارة، حالة المعايرة، والمصدرين — فالدليل
    وحده يكفي لمعرفة أيّ خصوصيّة اختيرت (نفس درس ``root_policy_variety``).
    """
    card = load_crop_card(crop)
    if card is None:
        return {"status": "blocked", "reason": "crop_card_missing", "crop": crop}
    stages = stage_nutrient_demand(crop)
    if not stages:
        return {"status": "blocked", "reason": "crop_card_nutrient_curves_missing", "crop": crop}

    requested_variety = (variety or "").strip()
    district_card = load_district(district_id) if district_id else None
    calibration_status = "absent"
    tier = "card_baseline"
    factors = {"n_factor": 1.0, "p_factor": 1.0, "k_factor": 1.0}
    sources: list[str] = [
        str(
            ((card.get("phenology") or {}).get("nutrient_demand_provenance") or {}).get(
                "primary_reference", ""
            )
        )
    ]

    if district_id and district_card is None:
        return {"status": "blocked", "reason": "district_unknown", "district_id": district_id}
    if district_card is not None:
        verdict = validate_district(district_card)
        if not verdict["valid"]:
            # منطقة فاسدة البنية لا تتدهور صامتةً إلى «بلا معايرة».
            return {
                "status": "blocked",
                "reason": "district_card_invalid",
                "district_id": district_id,
                "errors": verdict["errors"],
            }
        entries = _calibration_entries(district_card)
        chosen, tier = _pick_tier(entries, crop, requested_variety)
        if chosen is not None:
            calibration_status = "validated"
            factors = {k: float(chosen[k]) for k in ("n_factor", "p_factor", "k_factor")}
            sources.append(str(chosen.get("source", "")))
        elif any(e.get("crop") == crop for e in entries):
            calibration_status = "uncalibrated"

    return {
        "status": "resolved",
        "crop": crop,
        "district_id": district_id,
        "variety_requested": requested_variety or None,
        "tier": tier,
        "calibration_status": calibration_status,
        "locally_calibrated": calibration_status == "validated",
        "element_factors": factors,
        "stages": stages,
        "sources": [s for s in sources if s],
    }
