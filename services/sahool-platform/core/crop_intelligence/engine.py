from __future__ import annotations

import math
from typing import Any

from core.crop_intelligence.canonical_inputs import resolve_phenology_inputs
from core.crop_intelligence.confidence import compose_confidence
from core.crop_intelligence.crop_water import build_crop_water_state
from core.crop_intelligence.models import CropIntelligenceInput
from core.crop_intelligence.phenology import build_phenology_state
from core.crop_intelligence.policy_engine import evaluate_crop_policy
from core.crop_intelligence.recommendation_context import build_recommendation_context
from core.crop_intelligence.roots import build_root_state
from core.crop_intelligence.stress_memory import build_stress_memory
from core.season_phenology import resolve_crop_id

_SCHEMA = "crop_intelligence_state.v2"
_ENGINE_VERSION = "crop-intelligence/5.0.0"


def _finite_non_negative(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0:
        return None
    return value


def _availability(state: dict[str, Any] | None) -> str:
    if not state:
        return "unavailable"
    status = str(state.get("status") or state.get("quality_status") or "available")
    if status in {"insufficient", "unavailable", "invalid"}:
        return "unavailable"
    if status in {"degraded", "estimated", "inconsistent_inputs"}:
        return "degraded"
    return "available"


def build_crop_intelligence_state(inp: CropIntelligenceInput) -> dict[str, Any]:
    """Build the canonical crop-state read model from already-computed products.

    Ownership boundary: this function interprets crop response. It never computes
    ET0/VPD/GDD from raw weather and never fabricates biomass or yield.
    """
    crop_key = resolve_crop_id(inp.crop)
    crop_known = crop_key is not None
    canonical_phenology = resolve_phenology_inputs(
        crop=inp.crop,
        weather_state=inp.weather_state,
        legacy_gdd_cumulative=inp.gdd_cumulative,
        legacy_gdd_to_maturity=inp.gdd_to_maturity,
    )
    gdd = canonical_phenology["gdd_cumulative"]
    gdd_mat = canonical_phenology["gdd_to_maturity"]

    evidence_missing: list[str] = []
    if gdd is None:
        evidence_missing.append("gdd_cumulative")
    if gdd_mat is None or gdd_mat == 0:
        evidence_missing.append("gdd_to_maturity")

    phenology = build_phenology_state(
        gdd_cumulative=gdd,
        gdd_to_maturity=gdd_mat,
        method=canonical_phenology.get("method") or inp.phenology_method,
        formula_version=canonical_phenology.get("formula_version") or inp.phenology_formula_version,
        source_ids=list(dict.fromkeys([*inp.source_ids, *canonical_phenology["evidence_ids"]])),
    )
    progress = phenology.get("progress")

    water = dict(inp.water_state or {})
    nutrient = dict(inp.nutrient_state or {})
    vegetation = dict(inp.vegetation_state or {})
    spectral = dict(inp.spectral_state or {})
    weather = dict(inp.weather_state or {})
    soil = dict(inp.soil_state or {})

    spectral_confirmed = (
        spectral.get("water_stress", {}).get("confirmed") is True
        or vegetation.get("water_stress_confirmed") is True
    )

    limitations = [*inp.limitations, *canonical_phenology["limitations"]]
    if not crop_known:
        limitations.append("unknown_crop_uses_generic_crop_identity")
    if progress is None:
        limitations.append("phenology_unavailable")

    biomass = dict(inp.biomass_state or {})
    yield_state = dict(inp.yield_state or {})
    if not biomass:
        biomass = {"status": "unavailable", "reason": "no_validated_biomass_product"}
    if not yield_state:
        yield_state = {"status": "unavailable", "reason": "no_validated_yield_product"}

    root_policy = dict(inp.root_policy or {})
    root_state = build_root_state(
        phenology_progress=progress,
        initial_depth_m=root_policy.get("initial_depth_m"),
        maximum_depth_m=root_policy.get("maximum_depth_m"),
        effective_fraction=root_policy.get("effective_fraction", 0.8),
        policy_version=root_policy.get("policy_version"),
        source_ids=root_policy.get("source_ids") or inp.source_ids,
    )
    stress_memory_policy = dict(inp.stress_memory_policy or {})
    stress_memory = build_stress_memory(
        inp.stress_history,
        as_of=inp.stress_memory_as_of,
        half_life_days=stress_memory_policy.get("half_life_days", 7.0),
        max_age_days=stress_memory_policy.get("max_age_days", 45.0),
        source_ids=inp.source_ids,
        prior_snapshot=inp.prior_stress_memory,
    )

    crop_water_policy = dict(inp.crop_water_policy or {})
    et0_product = weather.get("et0") if isinstance(weather.get("et0"), dict) else {}
    crop_water = build_crop_water_state(
        et0_mm=et0_product.get("et0_mm") or weather.get("et0_mm"),
        crop_coefficient=crop_water_policy.get("crop_coefficient"),
        depletion_mm=water.get("depletion_mm"),
        raw_mm=water.get("raw_mm"),
        root_depth_m=root_state.get("current_depth_m"),
        policy_version=crop_water_policy.get("policy_version"),
        et0_method=et0_product.get("method") or weather.get("et0_method"),
        et0_quality_status=et0_product.get("quality_status") or weather.get("quality_status"),
        source_ids=(crop_water_policy.get("source_ids") or []) + inp.source_ids,
    )

    policy_assessment = evaluate_crop_policy(
        facts={
            "water_needs_irrigation": water.get("needs_irrigation") is True,
            "spectral_water_stress_confirmed": spectral_confirmed,
            "weather_heat_stress": weather.get("heat_stress") is True,
            "weather_frost_risk": weather.get("frost_risk") is True,
            "crop_water_urgency_high": crop_water.get("irrigation_urgency") == "high",
        }
    )
    stress_flags = policy_assessment["stress_flags"]

    component_status = {
        "phenology": _availability(phenology),
        "roots": _availability(root_state),
        "stress_memory": _availability(stress_memory),
        "crop_water": _availability(crop_water),
        "water": _availability(water),
        "nutrient": _availability(nutrient),
        "vegetation": _availability(vegetation),
        "spectral": _availability(spectral),
        "weather": _availability(weather),
        "soil": _availability(soil),
        "biomass": _availability(biomass),
        "yield": _availability(yield_state),
    }
    available_count = sum(v == "available" for v in component_status.values())
    degraded_count = sum(v == "degraded" for v in component_status.values())
    confidence = "medium" if available_count >= 4 and degraded_count == 0 else "low"
    recommendation_context = build_recommendation_context(
        phenology=phenology,
        crop_water=crop_water,
        stress_flags=stress_flags,
        stress_memory=stress_memory,
        component_status=component_status,
        source_ids=inp.source_ids,
        policy_assessment=policy_assessment,
    )

    return {
        "schema": _SCHEMA,
        "field_id": inp.field_id,
        "season_id": inp.season_id,
        "engine_version": _ENGINE_VERSION,
        "crop": crop_key or inp.crop,
        "crop_known": crop_known,
        "phenology": phenology,
        "root_state": root_state,
        "root_zone": water,
        "nutrient": nutrient,
        "vegetation": vegetation,
        "spectral": spectral,
        "weather": weather,
        "soil": soil,
        "biomass": biomass,
        "yield_projection": yield_state,
        "stress_flags": stress_flags,
        "policy_assessment": policy_assessment,
        "stress_memory": stress_memory,
        "crop_water": crop_water,
        "recommendation_context": recommendation_context,
        "component_status": component_status,
        "confidence": confidence,
        # عقد الثقة المُركَّب (P0-4): يُظهر العوامل والسقف الصادق بجوار السلسلة القائمة (توافق).
        "confidence_factors": compose_confidence(
            component_status,
            crop_known=crop_known,
            recommendation_status=recommendation_context.get("status"),
        ),
        "evidence_ids": list(
            dict.fromkeys([*inp.source_ids, *canonical_phenology["evidence_ids"]])
        ),
        "canonical_input_sources": {
            "weather": canonical_phenology["source"],
            "crop_knowledge": "governed_knowledge_layer"
            if canonical_phenology.get("knowledge_digest")
            else "unavailable",
        },
        "knowledge_provenance": {
            "knowledge_digest": canonical_phenology.get("knowledge_digest"),
            "evidence_ids": canonical_phenology.get("knowledge_evidence_ids") or [],
            "schema": "crop_knowledge_snapshot.v1"
            if canonical_phenology.get("knowledge_digest")
            else None,
        },
        "evidence_missing": evidence_missing,
        "limitations": list(dict.fromkeys(limitations)),
        "ownership": {
            "weather_products": "weather-service",
            "soil_products": "soil/field-state owners",
            "water_products": "water-ledger/irrigation domain",
            "vegetation_products": "vegetation-analysis-service",
            "crop_interpretation": "crop-intelligence-engine",
            "decisions": "decision-service",
        },
        "calibrated": False,
    }
