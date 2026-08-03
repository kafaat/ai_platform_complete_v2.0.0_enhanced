"""Production consumers for canonical agronomic states.

The adapters convert persisted canonical domain states into immutable
recommendation-candidate payloads. They do not recalculate domain truth and do
not approve or execute operations.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from api.canonical_nutrient_ledger import CanonicalNutrientLedger
from api.canonical_phenology_state import CanonicalPhenologyState
from api.canonical_salinity_state import CanonicalSalinityState


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class AgronomicStateCandidate:
    source_domain: str
    source_engine: str
    source_state_digest: str
    generated_at: datetime
    status: str
    action_type: str
    recommendation_code: str
    confidence: float
    operational_allowed: bool
    requires_human_approval: bool
    payload: Mapping[str, Any]
    evidence_digests: tuple[str, ...]
    constraints: tuple[str, ...]
    candidate_digest: str


def consume_phenology_state(state: CanonicalPhenologyState) -> AgronomicStateCandidate:
    """Turn canonical phenology into decision context without re-predicting stage."""
    blocked = state.status == "blocked" or state.canonical_stage is None
    constraints = tuple(sorted(set(state.limitations)))
    payload = {
        "canonical_stage": state.canonical_stage,
        "observed_stage": state.observed_stage,
        "predicted_stage": state.predicted_stage,
        "stage_divergence": state.stage_divergence,
        "days_since_sowing": state.days_since_sowing,
        "accumulated_gdd": state.accumulated_gdd,
        "gdd_fraction": state.gdd_fraction,
    }
    base = {
        "source_domain": "phenology",
        "source_engine": "canonical_phenology_state",
        "source_state_digest": state.state_digest,
        "generated_at": state.as_of.astimezone(UTC).isoformat(),
        "status": "blocked" if blocked else "ready",
        "action_type": "hold" if blocked else "monitor",
        "recommendation_code": "PHENOLOGY_REVIEW_REQUIRED"
        if blocked
        else "PHENOLOGY_CONTEXT_READY",
        "confidence": float(state.confidence or 0.0),
        "operational_allowed": False,
        "requires_human_approval": blocked,
        "payload": payload,
        "evidence_digests": sorted(state.evidence_digests),
        "constraints": list(constraints),
    }
    return AgronomicStateCandidate(
        **{
            **base,
            "generated_at": state.as_of.astimezone(UTC),
            "evidence_digests": tuple(base["evidence_digests"]),
            "constraints": constraints,
            "candidate_digest": _digest(base),
        }
    )


def consume_salinity_state(state: CanonicalSalinityState) -> AgronomicStateCandidate:
    """Convert salinity truth into a guarded leaching/monitoring candidate."""
    fraction = state.leaching_fraction
    leaching_needed = bool(
        state.operational_recommendation_allowed and fraction is not None and fraction > 0
    )
    blocked = state.status == "blocked"
    if leaching_needed:
        action = "irrigate"
        code = "SALINITY_LEACHING_REQUIRED"
    elif blocked:
        action = "hold"
        code = "SALINITY_EVIDENCE_OR_DRAINAGE_BLOCKED"
    else:
        action = "monitor"
        code = "SALINITY_MONITOR"
    payload = {
        "soil_class": state.soil_class,
        "water_risk": state.water_risk,
        "sodium_hazard_class": state.sodium_hazard_class,
        "rsc_hazard_class": state.rsc_hazard_class,
        "estimated_relative_yield": state.estimated_relative_yield,
        "leaching_fraction": fraction,
        "leaching_feasible": state.leaching_feasible,
        "drainage_class": state.drainage_class,
    }
    confidence = 1.0 if state.operational_recommendation_allowed else 0.5 if not blocked else 0.0
    base = {
        "source_domain": "salinity",
        "source_engine": "canonical_salinity_state",
        "source_state_digest": state.state_digest,
        "generated_at": state.as_of.astimezone(UTC).isoformat(),
        "status": "blocked"
        if blocked
        else "ready"
        if state.operational_recommendation_allowed
        else "degraded",
        "action_type": action,
        "recommendation_code": code,
        "confidence": confidence,
        "operational_allowed": leaching_needed,
        "requires_human_approval": leaching_needed,
        "payload": payload,
        "evidence_digests": sorted(state.evidence_digests),
        "constraints": sorted(state.limitations),
    }
    return AgronomicStateCandidate(
        **{
            **base,
            "generated_at": state.as_of.astimezone(UTC),
            "evidence_digests": tuple(base["evidence_digests"]),
            "constraints": tuple(base["constraints"]),
            "candidate_digest": _digest(base),
        }
    )


def consume_nutrient_ledger(ledger: CanonicalNutrientLedger) -> AgronomicStateCandidate:
    """Convert canonical N/P/K balances into one guarded fertilization candidate."""
    remaining = {
        item.nutrient: item.remaining_requirement_kg_ha
        for item in ledger.balances
        if item.remaining_requirement_kg_ha is not None and item.remaining_requirement_kg_ha > 0
    }
    fertilize = bool(ledger.operational_recommendation_allowed and remaining)
    blocked = ledger.status == "blocked"
    payload = {
        "phenology_stage": ledger.phenology_stage,
        "remaining_requirement_kg_ha": remaining,
        "balances": [asdict(item) for item in ledger.balances],
        "total_verified_cost": ledger.total_verified_cost,
        "currency": ledger.currency,
        "verified_operation_ids": list(ledger.verified_operation_ids),
    }
    base = {
        "source_domain": "nutrients",
        "source_engine": "canonical_nutrient_ledger",
        "source_state_digest": ledger.ledger_digest,
        "generated_at": ledger.as_of.astimezone(UTC).isoformat(),
        "status": "blocked"
        if blocked
        else "ready"
        if ledger.operational_recommendation_allowed
        else "degraded",
        "action_type": "fertilize" if fertilize else "hold" if blocked else "monitor",
        "recommendation_code": "NUTRIENT_APPLICATION_REQUIRED"
        if fertilize
        else "NUTRIENT_LEDGER_BLOCKED"
        if blocked
        else "NUTRIENT_BALANCE_MONITOR",
        "confidence": 1.0 if ledger.operational_recommendation_allowed else 0.0 if blocked else 0.5,
        "operational_allowed": fertilize,
        "requires_human_approval": fertilize,
        "payload": payload,
        "evidence_digests": sorted(ledger.evidence_digests),
        "constraints": sorted(ledger.limitations),
    }
    return AgronomicStateCandidate(
        **{
            **base,
            "generated_at": ledger.as_of.astimezone(UTC),
            "evidence_digests": tuple(base["evidence_digests"]),
            "constraints": tuple(base["constraints"]),
            "candidate_digest": _digest(base),
        }
    )
