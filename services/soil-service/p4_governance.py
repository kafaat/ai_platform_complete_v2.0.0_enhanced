"""Fine-grained evidence matrix and closed-loop soil outcome logic."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shared.contracts.soil.p4 import (
    SoilActionEvaluation,
    SoilActionPolicy,
    SoilExecutionRecord,
    SoilLearningAttribution,
    SoilOutcomeRecord,
)

RANK = {
    "baseline_only": 0,
    "modelled": 1,
    "analog_guided": 2,
    "field_observed": 3,
    "lab_verified": 4,
    "operational_verified": 5,
}
POLICIES = {
    "sampling_plan": SoilActionPolicy(action_type="sampling_plan"),
    "crop_suitability": SoilActionPolicy(
        action_type="crop_suitability",
        minimum_evidence_level="modelled",
        max_evidence_age_days=1095,
    ),
    "irrigation_guidance": SoilActionPolicy(
        action_type="irrigation_guidance",
        minimum_evidence_level="field_observed",
        required_properties=["field_capacity", "wilting_point"],
        max_evidence_age_days=365,
        required_depth_cm=60,
    ),
    "automatic_irrigation_execution": SoilActionPolicy(
        action_type="automatic_irrigation_execution",
        minimum_evidence_level="lab_verified",
        required_properties=["field_capacity", "wilting_point", "infiltration"],
        max_evidence_age_days=180,
        required_depth_cm=60,
        requires_water_profile=True,
        approval_requirement="agronomist",
    ),
    "fertilizer_rate": SoilActionPolicy(
        action_type="fertilizer_rate",
        minimum_evidence_level="lab_verified",
        required_properties=["ph", "ec", "organic_matter", "nitrogen", "phosphorus", "potassium"],
        max_evidence_age_days=365,
        required_depth_cm=30,
        approval_requirement="soil_specialist",
    ),
    "gypsum_rate": SoilActionPolicy(
        action_type="gypsum_rate",
        minimum_evidence_level="lab_verified",
        required_properties=["ec", "esp", "cec"],
        max_evidence_age_days=365,
        required_depth_cm=60,
        requires_water_profile=True,
        approval_requirement="soil_specialist",
    ),
    "leaching_requirement": SoilActionPolicy(
        action_type="leaching_requirement",
        minimum_evidence_level="lab_verified",
        required_properties=["ec", "field_capacity", "wilting_point", "infiltration"],
        max_evidence_age_days=180,
        required_depth_cm=90,
        requires_water_profile=True,
        requires_drainage_verification=True,
        approval_requirement="dual",
    ),
    "subsurface_drainage_design": SoilActionPolicy(
        action_type="subsurface_drainage_design",
        minimum_evidence_level="lab_verified",
        required_properties=["ksat", "water_table_depth"],
        max_evidence_age_days=180,
        required_depth_cm=150,
        requires_drainage_verification=True,
        approval_requirement="engineer",
    ),
    "reclamation_execution": SoilActionPolicy(
        action_type="reclamation_execution",
        minimum_evidence_level="lab_verified",
        required_properties=["ec", "ph"],
        max_evidence_age_days=180,
        requires_water_profile=True,
        requires_drainage_verification=True,
        approval_requirement="dual",
    ),
}


def evaluate_action(
    profile: dict[str, Any],
    action_type: str,
    *,
    water_profile_approved=False,
    drainage_verified=False,
    now=None,
) -> SoilActionEvaluation:
    p = POLICIES.get(action_type, SoilActionPolicy(action_type=action_type))
    reasons = []
    missing = []
    stale = []
    now = now or datetime.now(UTC)
    level = profile.get("evidence_level", "baseline_only")
    if RANK.get(level, -1) < RANK.get(p.minimum_evidence_level, 0):
        reasons.append("evidence_level_insufficient")
    props = profile.get("properties") or profile.get("values") or {}
    for name in p.required_properties:
        v = props.get(name)
        if v is None:
            missing.append(name)
            continue
        if p.max_evidence_age_days:
            ts = v.get("observed_at") if isinstance(v, dict) else None
            if ts:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if (now - dt).days > p.max_evidence_age_days:
                    stale.append(name)
    if missing:
        reasons.append("required_properties_missing")
    if stale:
        reasons.append("evidence_stale")
    if p.requires_water_profile and not water_profile_approved:
        reasons.append("approved_water_profile_required")
    if p.requires_drainage_verification and not drainage_verified:
        reasons.append("drainage_verification_required")
    if p.block_on_conflict and (profile.get("conflicts") or []):
        reasons.append("unresolved_soil_conflict")
    q = profile.get("quality_gate") or {}
    if q and not q.get("passed", True):
        reasons.append("soil_profile_quality_gate_failed")
    return SoilActionEvaluation(
        allowed=not reasons,
        code="soil_action_allowed" if not reasons else "soil_action_blocked",
        reasons=reasons,
        missing_properties=missing,
        stale_properties=stale,
        approval_requirement=p.approval_requirement,
    )


def build_learning(
    outcome: SoilOutcomeRecord, execution: SoilExecutionRecord, profile: dict[str, Any]
) -> SoilLearningAttribution:
    reasons = []
    if not execution.profile_hash:
        reasons.append("profile_lineage_missing")
    if not outcome.verification_id:
        reasons.append("verification_missing")
    if outcome.effectiveness_score < 0 or outcome.effectiveness_score > 1:
        reasons.append("invalid_effectiveness")
    return SoilLearningAttribution(
        tenant_id=outcome.tenant_id,
        field_id=outcome.field_id,
        outcome_id=outcome.outcome_id,
        execution_id=execution.execution_id,
        source_profile_hash=execution.profile_hash,
        action_type=execution.action_type,
        feature_snapshot={
            "evidence_level": profile.get("evidence_level"),
            "profile_hash": profile.get("profile_hash"),
            "properties": profile.get("properties", {}),
        },
        target_metrics={"effectiveness_score": outcome.effectiveness_score, **outcome.metrics},
        eligible_for_training=not reasons,
        exclusion_reasons=reasons,
    )
