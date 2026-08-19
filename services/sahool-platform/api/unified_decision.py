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

import hashlib
import json
import math
from typing import Any

SCHEMA_VERSION = "agronomic_decision_support.v1"


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def irrigation_closed_loop_advisory(
    *,
    field_state: dict[str, Any] | None,
    irrigation_plan: dict[str, Any],
    capacity: dict[str, Any] | None = None,
    economics: dict[str, Any] | None = None,
    outcome_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """AGRI-NEXT-1: constrain an existing irrigation plan without becoming an executor.

    The plan remains owned by the irrigation engine.  This helper only constrains the
    next proposed event by declared delivery capacity and surfaces energy/water cost.
    Outcome evidence is accepted only as a readiness signal; learning remains owned by
    ``irrigation_closed_loop_learning``.
    """
    days = list(irrigation_plan.get("days") or [])
    next_event = next((d for d in days if (_finite(d.get("irrigation_mm")) or 0.0) > 0), None)
    proposed_mm = _finite(next_event.get("irrigation_mm")) if next_event else 0.0
    proposed_mm = proposed_mm or 0.0

    limits: list[str] = []
    constrained_mm = proposed_mm
    cap_mm = _finite((capacity or {}).get("max_application_mm"))
    if cap_mm is not None and cap_mm >= 0:
        if constrained_mm > cap_mm:
            limits.append("application_capacity_limited")
        constrained_mm = min(constrained_mm, cap_mm)

    available_m3 = _finite((capacity or {}).get("remaining_volume_m3"))
    area_ha = _finite((capacity or {}).get("target_area_ha"))
    if available_m3 is not None and area_ha and area_ha > 0:
        volume_cap_mm = max(0.0, available_m3 / (10.0 * area_ha))
        if constrained_mm > volume_cap_mm:
            limits.append("remaining_volume_limited")
        constrained_mm = min(constrained_mm, volume_cap_mm)

    spectral = (field_state or {}).get("spectral") if isinstance(field_state, dict) else None
    water = (field_state or {}).get("water") if isinstance(field_state, dict) else None
    stress_class = None
    if isinstance(spectral, dict):
        stress_class = spectral.get("water_stress_class") or spectral.get("stress_class")
    if stress_class is None and isinstance(water, dict):
        stress_class = water.get("water_stress_class") or water.get("stress_class")

    water_price = _finite((economics or {}).get("water_price_per_m3"))
    energy_price = _finite((economics or {}).get("energy_price_per_kwh"))
    energy_kwh_m3 = _finite((capacity or {}).get("energy_kwh_per_m3"))
    event_m3 = constrained_mm * 10.0 * area_ha if area_ha and area_ha > 0 else None
    estimated_cost = None
    if event_m3 is not None:
        estimated_cost = 0.0
        if water_price is not None:
            estimated_cost += event_m3 * water_price
        if energy_price is not None and energy_kwh_m3 is not None:
            estimated_cost += event_m3 * energy_kwh_m3 * energy_price

    field_propose = ((field_state or {}).get("eligibility") or {}).get("propose", {})
    proposal_allowed = bool(field_propose.get("allowed", False)) if field_state else False
    reason_codes = (
        list(field_propose.get("reasons") or []) if field_state else ["field_state_missing"]
    )
    if proposed_mm > 0 and constrained_mm <= 0:
        reason_codes.append("delivery_capacity_zero")
    if irrigation_plan.get("budget_exhausted"):
        reason_codes.append("season_water_budget_exhausted")

    body = {
        "schema": f"{SCHEMA_VERSION}/irrigation-closed-loop",
        "next_event_day": next_event.get("day_index") if next_event else None,
        "engine_proposed_mm": round(proposed_mm, 3),
        "capacity_constrained_mm": round(constrained_mm, 3),
        "constraint_reasons": limits,
        "stress_class": stress_class,
        "estimated_event_m3": round(event_m3, 3) if event_m3 is not None else None,
        "estimated_water_energy_cost": round(estimated_cost, 4)
        if estimated_cost is not None
        else None,
        "proposal_allowed": proposal_allowed and not reason_codes,
        "direct_execution_permitted": False,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "outcome_evidence_present": isinstance(outcome_evidence, dict),
        "learning_auto_adjust_permitted": False,
    }
    return {**body, "evidence_digest": _digest(body)}


def canonical_agronomic_context(
    *,
    field_state: dict[str, Any] | None,
    crop_twin: dict[str, Any],
    operations: dict[str, Any] | None = None,
    economics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """AGRI-NEXT-2: one point-in-time envelope; never recompute owner facts."""
    field_state = field_state or {}
    body = {
        "schema": f"{SCHEMA_VERSION}/canonical-context",
        "field_id": field_state.get("field_id"),
        "season_id": field_state.get("season_id") or crop_twin.get("season_id"),
        "as_of_time": field_state.get("as_of_time") or crop_twin.get("as_of_time"),
        "crop": crop_twin.get("crop"),
        "phenology": crop_twin.get("phenology") or {},
        "availability": field_state.get("availability") or {},
        "eligibility": field_state.get("eligibility") or {},
        "owner_evidence_digests": field_state.get("evidence_digests") or {},
        "field_state_digest": field_state.get("state_digest"),
        "operations": operations or {"status": "not_supplied"},
        "economics": economics or {"status": "not_supplied"},
    }
    missing = [k for k in ("field_id", "as_of_time") if not body.get(k)]
    body["context_complete"] = not missing
    body["limitations"] = [f"{name}_missing" for name in missing]
    return {**body, "context_digest": _digest(body)}


def nutrient_salinity_ledger(
    *,
    soil_state: dict[str, Any] | None,
    irrigation_water: dict[str, Any] | None = None,
    nutrient_events: list[dict[str, Any]] | None = None,
    crop_demand_kg_ha: dict[str, float] | None = None,
) -> dict[str, Any]:
    """AGRI-NEXT-3: evidence ledger for nutrient balance and salinity constraints.

    Rates are not invented.  A nutrient is actionable only when both crop demand and
    applied mass are explicit.  Salinity risk is a declaration derived only from
    supplied EC values, never from a hidden default.
    """
    nutrient_events = nutrient_events or []
    applied: dict[str, float] = {}
    rejected = 0
    for event in nutrient_events:
        nutrient = str(event.get("nutrient") or "").lower()
        mass = _finite(event.get("kg_ha"))
        if not nutrient or mass is None or mass < 0:
            rejected += 1
            continue
        applied[nutrient] = applied.get(nutrient, 0.0) + mass

    balances: dict[str, dict[str, Any]] = {}
    for nutrient, demand_raw in sorted((crop_demand_kg_ha or {}).items()):
        demand = _finite(demand_raw)
        if demand is None or demand < 0:
            continue
        supplied = applied.get(nutrient.lower(), 0.0)
        balances[nutrient.lower()] = {
            "demand_kg_ha": round(demand, 3),
            "applied_kg_ha": round(supplied, 3),
            "remaining_kg_ha": round(max(0.0, demand - supplied), 3),
            "surplus_kg_ha": round(max(0.0, supplied - demand), 3),
        }

    ece = _finite((soil_state or {}).get("ece") or (soil_state or {}).get("soil_ece"))
    ecw = _finite((irrigation_water or {}).get("ecw") or (irrigation_water or {}).get("water_ec"))
    salinity_status = "unknown"
    if ece is not None or ecw is not None:
        # Classification only; no crop-specific threshold is invented here.
        salinity_status = (
            "measured_requires_crop_tolerance" if ece is not None else "water_ec_measured"
        )

    body = {
        "schema": f"{SCHEMA_VERSION}/nutrient-salinity-ledger",
        "balances": balances,
        "unmatched_applied_nutrients": {
            k: round(v, 3) for k, v in sorted(applied.items()) if k not in balances
        },
        "rejected_event_count": rejected,
        "soil_ece": ece,
        "water_ec": ecw,
        "salinity_status": salinity_status,
        "fertilizer_rate_authoritative": False,
        "requires_lab_or_declared_demand": not bool(balances),
    }
    return {**body, "ledger_digest": _digest(body)}


def spectral_action_candidate(
    *,
    spectral_state: dict[str, Any] | None,
    agronomic_context: dict[str, Any],
    proposed_action: str = "inspect_water_stress",
) -> dict[str, Any]:
    """AGRI-NEXT-4: satellite stress can nominate a candidate, never execute it."""
    spectral_state = spectral_state or {}
    quality = spectral_state.get("quality_status")
    stress = spectral_state.get("water_stress_class") or spectral_state.get("stress_class")
    propose_gate = (agronomic_context.get("eligibility") or {}).get("propose", {})
    reasons: list[str] = []
    if quality not in {"validated", "verified"}:
        reasons.append("spectral_quality_not_verified")
    if not stress or str(stress).lower() in {"normal", "none", "unknown"}:
        reasons.append("no_actionable_spectral_stress")
    if not bool(propose_gate.get("allowed", False)):
        reasons.extend(propose_gate.get("reasons") or ["agronomic_context_not_proposable"])

    body = {
        "schema": f"{SCHEMA_VERSION}/spectral-action-candidate",
        "action": proposed_action,
        "stress_class": stress,
        "candidate_status": "pending_decision" if not reasons else "evidence_required",
        "submit_to_decision": not reasons,
        "direct_action_permitted": False,
        "reason_codes": list(dict.fromkeys(reasons)),
        "context_digest": agronomic_context.get("context_digest"),
    }
    return {**body, "candidate_digest": _digest(body)}


def precision_yield_response(
    *,
    planned_rates: list[dict[str, Any]] | None,
    as_applied: list[dict[str, Any]] | None,
    yield_samples: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """AGRI-NEXT-5: compare planned/as-applied by zone and attach observed yield.

    This is attribution evidence, not causal proof and not a model-promotion signal.
    """
    planned_rates = planned_rates or []
    as_applied = as_applied or []
    yield_samples = yield_samples or []

    def by_zone(rows: list[dict[str, Any]], value_key: str) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {}
        for row in rows:
            zone = str(row.get("zone_id") or "")
            value = _finite(row.get(value_key))
            if zone and value is not None:
                out.setdefault(zone, []).append(value)
        return out

    planned = by_zone(planned_rates, "rate")
    applied = by_zone(as_applied, "rate")
    yields = by_zone(yield_samples, "yield_kg_ha")
    zones = sorted(set(planned) | set(applied) | set(yields))
    rows: list[dict[str, Any]] = []
    for zone in zones:
        p = sum(planned.get(zone, [])) / len(planned[zone]) if planned.get(zone) else None
        a = sum(applied.get(zone, [])) / len(applied[zone]) if applied.get(zone) else None
        y = sum(yields.get(zone, [])) / len(yields[zone]) if yields.get(zone) else None
        variance_pct = None
        if p is not None and p != 0 and a is not None:
            variance_pct = (a - p) / p * 100.0
        rows.append(
            {
                "zone_id": zone,
                "planned_rate": round(p, 4) if p is not None else None,
                "applied_rate": round(a, 4) if a is not None else None,
                "application_variance_pct": round(variance_pct, 3)
                if variance_pct is not None
                else None,
                "observed_yield_kg_ha": round(y, 3) if y is not None else None,
                "complete_triplet": p is not None and a is not None and y is not None,
            }
        )

    complete = sum(1 for row in rows if row["complete_triplet"])
    body = {
        "schema": f"{SCHEMA_VERSION}/precision-yield-response",
        "zones": rows,
        "complete_zone_count": complete,
        "zone_count": len(rows),
        "causal_claim_permitted": False,
        "automatic_model_promotion_eligible": False,
        "quality_status": "observed_response" if complete else "insufficient",
        "limitations": [] if complete else ["planned_as_applied_yield_triplet_incomplete"],
    }
    return {**body, "response_digest": _digest(body)}


# المدخلات الاقتصاديّة المطلوبة لاحقاً (طبقة economic_state مستقلّة).
_ECONOMIC_REQUIRED_INPUTS = ["crop_price", "water_cost", "energy_cost", "fertilizer_cost"]


def _water_risk(stress_days: int) -> str:
    return "منخفض" if stress_days == 0 else "متوسط" if stress_days <= 2 else "مرتفع"


def unified_decision(
    crop_twin: dict,
    irrigation_plan: dict,
    quality: dict,
    economic: dict | None = None,
    field_state: dict | None = None,
    irrigation_capacity: dict | None = None,
    irrigation_outcome: dict | None = None,
    irrigation_water: dict | None = None,
    nutrient_events: list[dict] | None = None,
    crop_demand_kg_ha: dict[str, float] | None = None,
    operations: dict | None = None,
    spectral_state: dict | None = None,
    planned_rates: list[dict] | None = None,
    as_applied: list[dict] | None = None,
    yield_samples: list[dict] | None = None,
) -> dict:
    """يؤلّف قراراً موحّداً من حالات محسوبة مسبقاً — نقيّ حتميّ.

    crop_twin: ناتج crop_twin_state. irrigation_plan: ناتج plan_irrigation.to_dict.
    quality: ناتج assess_data_quality. لا يعيد الحساب — يجمع ويصوغ التوصية.
    economic: كتلة economic_state إن توفّرت (تملأ المكان المحجوز)؛ وإلّا not_configured.
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

    agronomic_context = canonical_agronomic_context(
        field_state=field_state, crop_twin=crop_twin, operations=operations, economics=economic
    )
    irrigation_closure = irrigation_closed_loop_advisory(
        field_state=field_state,
        irrigation_plan=irrigation_plan,
        capacity=irrigation_capacity,
        economics=economic,
        outcome_evidence=irrigation_outcome,
    )
    soil_state = (field_state or {}).get("soil") if isinstance(field_state, dict) else None
    nutrient_ledger = nutrient_salinity_ledger(
        soil_state=soil_state,
        irrigation_water=irrigation_water,
        nutrient_events=nutrient_events,
        crop_demand_kg_ha=crop_demand_kg_ha,
    )
    spectral_candidate = spectral_action_candidate(
        spectral_state=spectral_state
        or ((field_state or {}).get("spectral") if isinstance(field_state, dict) else None),
        agronomic_context=agronomic_context,
    )
    yield_response = precision_yield_response(
        planned_rates=planned_rates, as_applied=as_applied, yield_samples=yield_samples
    )

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
        # الاقتصاد: يُملأ من economic_state إن مُرِّر، وإلّا محجوز صراحةً (لا مُختلق).
        "economic_state": economic
        if economic is not None
        else {
            "status": "not_configured",
            "required_inputs": list(_ECONOMIC_REQUIRED_INPUTS),
        },
        "calibrated": False,
        "warnings_ar": list(crop_twin.get("warnings_ar", [])) + list(plan.get("notes_ar", [])),
        "agronomic_context": agronomic_context,
        "irrigation_closed_loop": irrigation_closure,
        "nutrient_salinity_ledger": nutrient_ledger,
        "spectral_action_candidate": spectral_candidate,
        "precision_yield_response": yield_response,
    }
