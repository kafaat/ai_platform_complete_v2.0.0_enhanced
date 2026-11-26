"""Pure P3 product builders with conservative, fail-closed governance."""

from __future__ import annotations

import hashlib
import math
from statistics import fmean

from land_quality import classify_salinity_sodicity, gypsum_requirement, land_capability

from shared.contracts.soil.p3 import (
    AnalogFieldProduct,
    AnalogFieldRequest,
    AnalogPropertyEstimate,
    DrainageAssessmentProduct,
    DrainageAssessmentRequest,
    MobileSoilImageRequest,
    ReclamationAssessmentProduct,
    ReclamationAssessmentRequest,
    ReclamationEconomicsProduct,
    ReclamationEconomicsRequest,
    ReclamationScenario,
    SoilVisualObservation,
)

# v2: a lab product whose gypsum candidate lists missing rate inputs now blocks gypsum_rate.
# The stored payload means something different from v1, so the version key changes rather
# than an identical resubmission silently overwriting a v1 product (p3_store upsert key).
LAB_HB60_VERSION_SUFFIX = "lab-hb60.v2"


def build_mobile_visual_observation(req: MobileSoilImageRequest) -> SoilVisualObservation:
    q = req.quality
    reasons: list[str] = []
    if q.blur_score < 0.65:
        reasons.append("image_blur")
    if q.exposure_score < 0.65:
        reasons.append("invalid_exposure")
    if q.shadow_fraction > 0.25:
        reasons.append("excessive_shadow")
    if not q.reference_card_detected:
        reasons.append("reference_card_missing")
    if not q.scale_marker_detected:
        reasons.append("scale_marker_missing")
    if q.gps_accuracy_m > 15:
        reasons.append("gps_accuracy_insufficient")
    gate = not reasons
    pred = req.prediction
    confidence = min(
        q.blur_score, q.exposure_score, 1 - q.shadow_fraction, pred.segmentation_confidence
    )
    review_required = (
        not gate
        or confidence < 0.75
        or max(
            pred.salt_crust_probability,
            pred.surface_crack_probability,
            pred.coarse_fragment_probability,
            pred.waterlogging_probability,
        )
        in (0.0, 1.0)
    )
    accepted = (
        {}
        if not gate or req.review_status == "rejected"
        else {
            "salt_crust_probability": pred.salt_crust_probability,
            "surface_crack_probability": pred.surface_crack_probability,
            "coarse_fragment_probability": pred.coarse_fragment_probability,
            "waterlogging_probability": pred.waterlogging_probability,
            "color_class": pred.color_class or "unknown",
        }
    )
    blocked = ["fertilizer_rate", "gypsum_rate", "leaching_requirement", "reclamation_execution"]
    return SoilVisualObservation(
        tenant_id=req.tenant_id,
        field_id=req.field_id,
        image_id=req.image_id,
        object_uri=req.object_uri,
        captured_at=req.captured_at,
        depth_cm=req.depth_cm,
        quality_gate_passed=gate,
        quality_reasons=reasons,
        review_required=review_required,
        review_status=req.review_status,
        accepted_predictions=accepted,
        blocked_use=blocked,
        confidence=max(0.0, min(1.0, confidence if gate else confidence * 0.4)),
        provenance={
            "model_version": req.model_version,
            "surface_moisture_state": req.surface_moisture_state,
            "latitude": req.latitude,
            "longitude": req.longitude,
            "original_image_preserved": True,
        },
    )


def _flat_distance(target: dict[str, dict[str, float]], candidate) -> float:
    groups = ["terrain", "climate", "soilgrids", "spectral", "crop_history", "irrigation_water"]
    diffs = []
    for group in groups:
        tv = target.get(group, {})
        cv = getattr(candidate, group, {})
        for key, val in tv.items():
            if key in cv:
                scale = max(abs(val), abs(cv[key]), 1.0)
                diffs.append(((val - cv[key]) / scale) ** 2)
    return math.sqrt(sum(diffs) / len(diffs)) if diffs else 2.0


def build_analog_field_product(req: AnalogFieldRequest) -> AnalogFieldProduct:
    ranked = []
    for c in req.candidates:
        d = _flat_distance(req.target_features, c)
        if d <= req.max_distance:
            ranked.append((d, c))
    ranked.sort(key=lambda x: x[0])
    cohort = ranked[: req.max_candidates]
    out_of_domain = len(cohort) < req.minimum_cohort_size
    estimates = []
    for prop in req.requested_properties:
        vals = []
        for d, c in cohort:
            if prop in c.trusted_properties:
                weight = max(1e-6, (1 - d) * c.evidence_quality)
                vals.append((c.trusted_properties[prop], weight, d))
        if len(vals) < req.minimum_cohort_size:
            estimates.append(
                AnalogPropertyEstimate(
                    property_name=prop,
                    estimated_value=None,
                    uncertainty=1.0,
                    cohort_size=len(vals),
                    status="out_of_domain" if out_of_domain else "insufficient_cohort",
                )
            )
            continue
        total = sum(w for _, w, _ in vals)
        estimate = sum(v * w for v, w, _ in vals) / total
        spread = math.sqrt(sum(w * (v - estimate) ** 2 for v, w, _ in vals) / total)
        norm = max(abs(estimate), 1.0)
        uncertainty = min(1.0, 0.25 + spread / norm + fmean(d for _, _, d in vals) * 0.5)
        estimates.append(
            AnalogPropertyEstimate(
                property_name=prop,
                estimated_value=estimate,
                uncertainty=uncertainty,
                cohort_size=len(vals),
                status="estimated",
            )
        )
    anon = []
    for d, c in cohort:
        anon.append(
            {
                "cohort_member": hashlib.sha256(c.field_id.encode()).hexdigest()[:12],
                "distance": round(d, 5),
                "evidence_quality": c.evidence_quality,
            }
        )
    return AnalogFieldProduct(
        tenant_id=req.tenant_id,
        field_id=req.field_id,
        model_version=req.model_version,
        anonymized_cohort=anon,
        estimates=estimates,
        out_of_domain=out_of_domain,
        blocked_use=[
            "fertilizer_rate",
            "gypsum_rate",
            "automatic_irrigation_execution",
            "reclamation_execution",
        ],
        provenance={
            "minimum_cohort_size": req.minimum_cohort_size,
            "max_distance": req.max_distance,
            "privacy": "field identifiers hashed; tenant groups not emitted",
            "evidence_class": "modelled",
        },
    )


# Waterlogging-risk weights.  They must sum to 1.0 so the weighted sum stays
# in [0, 1] without clipping (which would flatten the monotonic response).
_DRAINAGE_RISK_WEIGHTS = {
    "water_table": 0.16,
    "impermeable_layer": 0.12,
    "depression": 0.13,
    "ksat": 0.11,
    "gradient": 0.09,
    "outlet": 0.10,
    "flood": 0.11,
    "wadi": 0.07,
    "salinity_persistence": 0.11,
}

# Unknown hydrology is not evidence of good drainage: an unmeasured water
# table / impermeable layer scores a neutral prior instead of zero risk.
_UNKNOWN_WATER_TABLE_RISK = 0.5
_UNKNOWN_IMPERMEABLE_RISK = 0.5
_UNKNOWN_KSAT_RISK = 0.45


def _water_table_risk(depth_m: float | None) -> float | None:
    if depth_m is None:
        return None
    return max(0.0, min(1.0, (2.0 - depth_m) / 2.0))


def _impermeable_risk(depth_m: float | None) -> float | None:
    if depth_m is None:
        return None
    return max(0.0, min(1.0, (1.2 - depth_m) / 1.2))


def build_drainage_assessment(req: DrainageAssessmentRequest) -> DrainageAssessmentProduct:
    wt_observed = _water_table_risk(req.water_table_depth_m)
    impermeable_observed = _impermeable_risk(req.impermeable_layer_depth_m)
    wt = _UNKNOWN_WATER_TABLE_RISK if wt_observed is None else wt_observed
    impermeable = (
        _UNKNOWN_IMPERMEABLE_RISK if impermeable_observed is None else impermeable_observed
    )
    ksat = (
        _UNKNOWN_KSAT_RISK
        if req.ksat_mm_h is None
        else max(0.0, min(1.0, (10 - req.ksat_mm_h) / 10))
    )
    gradient_risk = max(0.0, min(1.0, (0.5 - req.mean_drainage_gradient_pct) / 0.5))
    # A poor natural outlet means surface water has nowhere to go.
    outlet_risk = 1.0 - req.natural_outlet_score
    w = _DRAINAGE_RISK_WEIGHTS
    risk = min(
        1.0,
        w["water_table"] * wt
        + w["impermeable_layer"] * impermeable
        + w["depression"] * req.depression_fraction
        + w["ksat"] * ksat
        + w["gradient"] * gradient_risk
        + w["outlet"] * outlet_risk
        + w["flood"] * req.flood_risk
        + w["wadi"] * req.wadi_risk
        + w["salinity_persistence"] * req.salinity_persistence,
    )
    poor_outlet = req.natural_outlet_score < 0.3
    surface = (
        req.depression_fraction > 0.2
        or req.flood_risk > 0.55
        # Without a natural outlet even moderate ponding / flood exposure
        # needs surface works.
        or (poor_outlet and (req.depression_fraction > 0.1 or req.flood_risk > 0.35))
    )
    # Engineering triggers use measured evidence only; priors for unknown
    # depths raise the screening risk but never assert a subsurface need.
    subsurface = (
        (wt_observed is not None and wt_observed > 0.45)
        or (impermeable_observed is not None and impermeable_observed > 0.55)
        or (ksat > 0.55 and req.salinity_persistence > 0.5)
    )
    need = (
        "combined"
        if surface and subsurface
        else "surface"
        if surface
        else "subsurface"
        if subsurface
        else "monitor"
        if risk > 0.28
        else "none"
    )
    limitations = []
    if req.water_table_depth_m is None:
        limitations.append("water_table_depth_unknown")
        if need == "none":
            # No water-table evidence: "no drainage need" cannot be asserted.
            need = "monitor"
            limitations.append("insufficient_evidence_for_no_drainage_need")
    if req.impermeable_layer_depth_m is None:
        limitations.append("impermeable_layer_depth_unknown")
    if req.ksat_mm_h is None:
        limitations.append("ksat_unknown")
    prereq = []
    blocked = []
    if not req.surveyed_elevations:
        prereq.append("surveyed_elevation_model")
        blocked.append("subsurface_drainage_design")
    if req.ksat_mm_h is None:
        prereq.append("field_ksat_or_infiltration_test")
        blocked.append("drain_spacing_execution")
    if req.water_table_depth_m is None:
        prereq.append("seasonal_water_table_monitoring")
    rec = []
    if surface:
        rec.append("grade local depressions and maintain surface outlets")
    if surface and poor_outlet:
        rec.append("establish or improve a natural drainage outlet before surface works")
    if subsurface:
        rec.append("commission engineering subsurface drainage study")
    if req.wadi_risk > 0.5:
        rec.append("protect drainage outlets from wadi backflow and erosion")
    confidence = (
        0.9
        - 0.18 * (req.ksat_mm_h is None)
        - 0.14 * (req.water_table_depth_m is None)
        - 0.2 * (not req.surveyed_elevations)
    )
    return DrainageAssessmentProduct(
        tenant_id=req.tenant_id,
        field_id=req.field_id,
        geometry_hash=req.geometry_hash,
        assessment_version=req.assessment_version,
        drainage_need=need,
        waterlogging_risk=risk,
        engineering_confidence=max(0.1, confidence),
        prerequisites=prereq,
        recommendations=rec,
        blocked_actions=sorted(set(blocked)),
        limitations=limitations,
        provenance={
            "method": "governed_multi_evidence_screening",
            "engineering_design": False,
            "requires_field_verification": True,
            "risk_weights": dict(_DRAINAGE_RISK_WEIGHTS),
        },
    )


class DrainageNeedConflict(ValueError):
    """Caller-asserted drainage_need contradicts the stored drainage assessment."""


def reconcile_reclamation_drainage_need(requested: str, stored_assessment: dict | None) -> dict:
    """Check a reclamation request's drainage_need against the stored assessment.

    Returns provenance fields describing where drainage_need came from.  A
    stored assessment for the same tenant/field is authoritative: a request
    that contradicts it raises :class:`DrainageNeedConflict` so the caller
    cannot downgrade the drainage block.  Without one, the caller's value is
    kept but flagged as unverified.
    """
    if stored_assessment is None:
        return {
            "drainage_need_source": "caller_asserted",
            "limitations": ["drainage_need_not_backed_by_stored_assessment"],
        }
    stored_need = stored_assessment.get("drainage_need")
    if stored_need != requested:
        raise DrainageNeedConflict(
            f"drainage_need '{requested}' contradicts stored drainage assessment "
            f"('{stored_need}'); re-run the drainage assessment first"
        )
    return {
        "drainage_need_source": "stored_drainage_assessment",
        "drainage_assessment_product_id": stored_assessment.get("product_id"),
        "limitations": [],
    }


def _gypsum_scenario(
    req: ReclamationAssessmentRequest, candidate: bool, esp_evidence_usable: bool
) -> dict | None:
    scenario = req.gypsum_scenario
    if scenario is None:
        return None
    report = {
        "status": "not_evaluated",
        "estimate": None,
        "input_basis": scenario.input_basis,
        "source_ref": scenario.source_ref,
        "input_quality": "caller_supplied_unverified",
        "execution_authorized": False,
        "local_compliance_evaluated": False,
    }
    if not req.lab_verified or req.esp_pct is None:
        return {**report, "reason": "missing_declared_lab_esp"}
    if not esp_evidence_usable:
        return {**report, "reason": "esp_sample_not_evaluated"}
    if not candidate:
        return {**report, "reason": "no_gypsum_candidate"}
    try:
        result = gypsum_requirement(
            cec_cmolc_kg=scenario.cec_cmolc_kg,
            esp_initial_pct=req.esp_pct,
            esp_target_pct=scenario.esp_target_pct,
            depth_m=scenario.depth_m,
            bulk_density_t_m3=scenario.bulk_density_t_m3,
            purity=scenario.purity,
            exchange_efficiency_factor=scenario.exchange_efficiency_factor,
            esp_basis="caller_declared_lab_esp",
        )
        if not all(
            math.isfinite(value)
            for value in (
                result.gypsum_t_per_ha,
                result.na_to_replace_cmolc_kg,
                result.soil_mass_t_per_ha,
            )
        ):
            return {**report, "reason": "nonfinite_estimate"}
    except (ValueError, OverflowError):
        return {**report, "reason": "invalid_estimate_inputs"}
    return {**report, "status": "estimated", "estimate": result.to_dict()}


def _land_capability_scenario(req: ReclamationAssessmentRequest) -> dict | None:
    scenario = req.land_capability_scenario
    if scenario is None:
        return None
    result = land_capability(
        slope_pct=scenario.slope_pct,
        effective_depth_cm=scenario.effective_depth_cm,
        ece_ds_m=scenario.ece_ds_m if scenario.ec_method == "saturation_extract_25c" else None,
        esp_pct=scenario.esp_pct,
        drainage_class=scenario.drainage_class,
    )
    return {
        "status": "estimated" if result.complete else "incomplete",
        "inputs": scenario.model_dump(mode="json"),
        "input_quality": "caller_supplied_unverified",
        "result": result.to_dict(),
        "execution_authorized": False,
        "local_compliance_evaluated": False,
    }


def build_reclamation_assessment(req: ReclamationAssessmentRequest) -> ReclamationAssessmentProduct:
    severity = max(
        req.salinity_probability,
        req.sodicity_probability,
        req.compaction_risk,
        req.leveling_need,
        req.stoniness_fraction,
        0.75
        if req.drainage_need in {"subsurface", "combined"}
        else 0.35
        if req.drainage_need == "surface"
        else 0,
    )
    suitability = (
        "suitable"
        if severity < 0.25 and req.crop_suitability_score > 0.7
        else "conditionally_suitable"
        if severity < 0.55
        else "marginal"
        if severity < 0.8
        else "not_currently_suitable"
    )
    priority = (
        "critical"
        if severity >= 0.85
        else "high"
        if severity >= 0.65
        else "medium"
        if severity >= 0.35
        else "low"
    )
    interventions = []
    if req.leveling_need > 0.4:
        interventions.append({"type": "precision_leveling", "priority": req.leveling_need})
    if req.drainage_need not in {"none", "monitor"}:
        interventions.append({"type": "drainage", "mode": req.drainage_need})
    if req.salinity_probability > 0.45:
        interventions.append(
            {"type": "leaching_candidate", "requires": "approved_water_and_drainage"}
        )
    # Reuse the versioned HB60 clauses, including their measurement method and
    # freshness gates. Legacy requests retain the previous partial evaluation.
    sample = req.lab_sample
    lab_class = None
    if req.lab_verified and (req.ec_lab_ds_m is not None or req.esp_pct is not None):
        lab_class = classify_salinity_sodicity(
            ece_ds_m=req.ec_lab_ds_m,
            ec_method=sample.ec_method if sample else None,
            esp_pct=req.esp_pct,
            observed_on=sample.observed_on if sample else None,
            source=sample.source_ref if sample else f"reclamation_request:{req.field_id}",
        )
    lab_sodic = bool(lab_class and lab_class.sodic is True)
    lab_saline = bool(lab_class and lab_class.saline is True)
    if req.salinity_probability <= 0.45 and lab_saline:
        interventions.append(
            {
                "type": "leaching_candidate",
                "requires": "approved_water_and_drainage",
                "basis": "lab_hb60",
            }
        )
    gypsum_rate_inputs_missing = False
    if req.sodicity_probability > 0.45 or lab_sodic:
        gypsum = {"type": "gypsum_candidate", "requires": "lab_EC_ESP_and_water_profile"}
        if lab_sodic:
            gypsum["basis"] = "lab_hb60"
        if req.esp_pct is not None and req.lab_verified:
            # The rate kernel exists (land_quality.gypsum_requirement) but this request
            # contract carries no CEC, depth or bulk density — name what is missing rather
            # than emit a rate from assumed values. Unverified ESP is not echoed.
            gypsum["esp_pct"] = req.esp_pct
            gypsum["rate_kernel"] = "land_quality.gypsum_requirement"
            gypsum["rate_inputs_missing"] = ["cec_cmolc_kg", "depth_m", "bulk_density_t_m3"]
            gypsum_rate_inputs_missing = True
        interventions.append(gypsum)
    if req.compaction_risk > 0.55:
        interventions.append(
            {"type": "subsoiling_candidate", "requires": "field_compaction_verification"}
        )
    if req.stoniness_fraction > 0.25:
        interventions.append({"type": "stone_removal", "fraction": req.stoniness_fraction})
    blocked = []
    allowed = ["sampling", "monitoring", "crop_suitability_screening"]
    if not req.lab_verified:
        blocked += ["gypsum_rate", "leaching_requirement", "reclamation_execution"]
    if not req.irrigation_water_profile_approved:
        blocked += ["leaching_requirement", "gypsum_rate"]
    if req.drainage_need not in {"none", "monitor"} and not req.drainage_engineering_verified:
        blocked += ["reclamation_execution", "subsurface_drainage_design"]
    if not blocked:
        allowed += ["gypsum_rate", "leaching_requirement", "reclamation_execution"]
    if gypsum_rate_inputs_missing:
        # The candidate itself says a rate cannot be computed from this request, so the
        # assessment must not also allow one. Added AFTER the gate above, so blocking the
        # rate does not switch off leaching or reclamation execution as a side effect.
        blocked.append("gypsum_rate")
    if sample is not None:
        # A caller-provided sample reference is not an independently verified
        # local adoption or work approval; this new path is diagnostic only.
        blocked.extend(["gypsum_rate", "leaching_requirement", "reclamation_execution"])
    gypsum_scenario = _gypsum_scenario(
        req,
        req.sodicity_probability > 0.45 or lab_sodic,
        sample is None or bool(lab_class and lab_class.sodic is not None),
    )
    if gypsum_scenario is not None:
        # An unverified planning scenario cannot authorize a rate or field execution.
        blocked.extend(["gypsum_rate", "reclamation_execution"])
    capability = _land_capability_scenario(req)
    if capability is not None:
        # An indicative scenario must not authorize field execution.
        blocked.append("reclamation_execution")
    phases = [
        {
            "phase": 1,
            "name": "verification",
            "actions": ["lab confirmation", "water analysis", "topographic survey"],
        },
        {
            "phase": 2,
            "name": "enabling works",
            "actions": [
                i["type"]
                for i in interventions
                if i["type"] in {"precision_leveling", "drainage", "stone_removal"}
            ],
        },
        {
            "phase": 3,
            "name": "soil amendment",
            "actions": [
                i["type"]
                for i in interventions
                if i["type"] in {"gypsum_candidate", "leaching_candidate", "subsoiling_candidate"}
            ],
        },
        {
            "phase": 4,
            "name": "verification and cropping",
            "actions": ["post-treatment sampling", "establishment crop", "outcome monitoring"],
        },
    ]
    confidence = (
        0.45
        + 0.2 * req.lab_verified
        + 0.15 * req.irrigation_water_profile_approved
        + 0.15 * req.drainage_engineering_verified
    )
    # A product carrying the lab HB60 classification has different output semantics from a
    # pre-Phase-2 product; p3_store upserts on (…, version, identity_hash), so the version key
    # must change or an identical resubmission would silently overwrite the stored payload.
    return ReclamationAssessmentProduct(
        tenant_id=req.tenant_id,
        field_id=req.field_id,
        geometry_hash=req.geometry_hash,
        assessment_version=(
            req.assessment_version
            + (f"+{LAB_HB60_VERSION_SUFFIX}" if lab_class else "")
            + ("+lab-sample.v1" if sample is not None else "")
            + ("+gypsum-scenario.v1" if gypsum_scenario is not None else "")
            + ("+land-capability.v1" if capability is not None else "")
        ),
        suitability_class=suitability,
        reclamation_priority=priority,
        interventions=interventions,
        phased_plan=phases,
        allowed_actions=sorted(set(allowed) - set(blocked)),
        blocked_actions=sorted(set(blocked)),
        confidence=min(0.95, confidence),
        provenance={
            "evidence_gate": "fail_closed",
            "lab_verified": req.lab_verified,
            "water_profile_approved": req.irrigation_water_profile_approved,
            "drainage_engineering_verified": req.drainage_engineering_verified,
            **({"lab_salinity_sodicity": lab_class.to_dict()} if lab_class else {}),
            **(
                {
                    "lab_sample": {
                        **sample.model_dump(mode="json"),
                        "input_quality": "caller_supplied_unverified",
                        "local_compliance_evaluated": False,
                        "execution_authorized": False,
                    }
                }
                if sample is not None
                else {}
            ),
            **({"gypsum_scenario": gypsum_scenario} if gypsum_scenario is not None else {}),
            **({"land_capability_scenario": capability} if capability is not None else {}),
        },
    )


def _npv(capex, annual_net, rate, years):
    return -capex + sum(annual_net / ((1 + rate) ** y) for y in range(1, years + 1))


def build_reclamation_economics(req: ReclamationEconomicsRequest) -> ReclamationEconomicsProduct:
    base_water = req.water_m3_per_ha * req.water_cost_per_m3 * req.area_ha
    base_energy = req.energy_kwh_per_ha * req.energy_cost_per_kwh * req.area_ha
    base_gypsum = req.gypsum_t_per_ha * req.gypsum_cost_per_tonne * req.area_ha
    enable = (
        (req.drainage_cost_per_ha * req.area_ha if req.drainage_required else 0)
        + (req.leveling_cost_per_ha * req.area_ha if req.leveling_required else 0)
        + (req.stone_removal_cost_per_ha * req.area_ha if req.stone_removal_required else 0)
    )
    benefit = req.expected_annual_margin_per_ha * req.area_ha
    configs = {
        "minimum": {"capex_factor": 0.35, "benefit_factor": 0.45, "risk": 0.55, "years": 1.0},
        "balanced": {"capex_factor": 0.70, "benefit_factor": 0.75, "risk": 0.78, "years": 2.0},
        "full": {"capex_factor": 1.0, "benefit_factor": 1.0, "risk": 0.88, "years": 3.0},
    }
    scenarios = []
    for name, c in configs.items():
        capex = (enable + base_gypsum) * c["capex_factor"]
        annual_opex = (base_water + base_energy) * (0.75 + 0.25 * c["capex_factor"])
        annual_benefit = benefit * c["benefit_factor"]
        net = annual_benefit - annual_opex
        payback = None if net <= 0 else capex / net
        npv = _npv(capex, net, req.discount_rate, req.horizon_years)
        scenarios.append(
            ReclamationScenario(
                name=name,
                capex=round(capex, 2),
                annual_opex=round(annual_opex, 2),
                expected_annual_benefit=round(annual_benefit, 2),
                payback_years=None if payback is None else round(payback, 2),
                npv=round(npv, 2),
                risk_adjusted_npv=round(npv * c["risk"], 2),
                implementation_years=c["years"],
                assumptions={"benefit_realization": c["benefit_factor"], "risk_factor": c["risk"]},
            )
        )
    viable = [s for s in scenarios if s.risk_adjusted_npv > 0]
    recommended = max(viable, key=lambda s: s.risk_adjusted_npv).name if viable else None
    return ReclamationEconomicsProduct(
        tenant_id=req.tenant_id,
        field_id=req.field_id,
        currency=req.currency,
        scenarios=scenarios,
        recommended_scenario=recommended,
        provenance={
            "discount_rate": req.discount_rate,
            "horizon_years": req.horizon_years,
            "method": "risk_adjusted_discounted_cash_flow",
            "not_a_financial_guarantee": True,
        },
    )
