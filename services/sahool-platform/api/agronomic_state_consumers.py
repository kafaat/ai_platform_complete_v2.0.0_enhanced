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
from datetime import UTC, datetime, timedelta
from typing import Any

from api.canonical_nutrient_ledger import CanonicalNutrientLedger
from api.canonical_phenology_state import CanonicalPhenologyState
from api.canonical_salinity_state import CanonicalSalinityState

_NUTRIENT_CONFIDENCE_PENALTY = 0.15
# A persisted ledger is a snapshot at ``as_of``: applications and phenology after it
# are not in its balance.  Two weeks is about one split-N interval / phenology
# sub-stage; an older ledger is shown for context but cannot drive fertilization.
NUTRIENT_LEDGER_MAX_AGE = timedelta(days=14)
# Clock skew tolerated before an ``as_of`` in the future is treated as invalid.
_NUTRIENT_LEDGER_FUTURE_SKEW = timedelta(minutes=5)


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


def _crop_identity_limitation(request_crop: str, ledger_crop: str) -> str | None:
    """Compare crops by canonical card id, not by spelling.

    The request carries a display name (``req.crop``: «قمح صلب», «ذرة صفراء» from the
    web/mobile pickers) while the ledger carries whatever crop id its builder was given,
    so both sides go through the platform's one crop resolver (card ``crop_id`` ·
    ``name_ar`` · ``name_en`` · ``aliases``).  A side that does not resolve is not
    evidence of a *different* crop, but it is no proof of the same one either: it
    stays blocked under its own reason.
    """
    from core.season_phenology import resolve_crop_id

    requested, built_for = resolve_crop_id(request_crop), resolve_crop_id(ledger_crop)
    if requested is None or built_for is None:
        return "NUTRIENT_LEDGER_CROP_UNRESOLVED"
    return None if requested == built_for else "NUTRIENT_LEDGER_CROP_MISMATCH"


def consume_nutrient_ledger(
    ledger: CanonicalNutrientLedger,
    *,
    now: datetime | None = None,
    crop_id: str | None = None,
) -> AgronomicStateCandidate:
    """Convert canonical N/P/K balances into one guarded fertilization candidate.

    With ``now`` the ledger is blocked when older than ``NUTRIENT_LEDGER_MAX_AGE`` (or
    dated in the future); with ``crop_id`` it is blocked unless both crops resolve to
    the same canonical card id (``NUTRIENT_LEDGER_CROP_MISMATCH`` when they resolve to
    different crops, ``NUTRIENT_LEDGER_CROP_UNRESOLVED`` when either does not resolve).
    Production callers pass both.
    """
    freshness: list[str] = []
    if now is not None:
        age = now.astimezone(UTC) - ledger.as_of.astimezone(UTC)
        if age > NUTRIENT_LEDGER_MAX_AGE:
            freshness.append("NUTRIENT_LEDGER_STALE")
        elif age < -_NUTRIENT_LEDGER_FUTURE_SKEW:
            freshness.append("NUTRIENT_LEDGER_FROM_FUTURE")
    if crop_id is not None:
        crop_problem = _crop_identity_limitation(crop_id, ledger.crop_id)
        if crop_problem:
            freshness.append(crop_problem)
    # Only balances with known soil supply AND known demand are actionable; an
    # unknown soil value must never be read as zero supply (full-demand advice).
    actionable = [item for item in ledger.balances if item.actionable]
    non_actionable = sorted(
        {item.nutrient for item in ledger.balances} - {item.nutrient for item in actionable}
    )
    remaining = {
        item.nutrient: item.remaining_requirement_kg_ha
        for item in actionable
        if item.remaining_requirement_kg_ha > 0
    }
    blocked = ledger.status == "blocked" or bool(freshness)
    fertilize = bool(ledger.operational_recommendation_allowed and remaining and not blocked)
    limitations = sorted(set(ledger.limitations) | set(freshness))
    if blocked:
        status = "blocked"
        confidence = 0.0
    else:
        partial = bool(limitations or non_actionable)
        status = "degraded" if partial or not ledger.operational_recommendation_allowed else "ready"
        # Each limitation costs confidence; 1.0 is reserved for complete evidence.
        penalty = _NUTRIENT_CONFIDENCE_PENALTY * max(len(limitations), len(non_actionable))
        confidence = round(max(0.0, 1.0 - penalty), 6)
    payload = {
        "phenology_stage": ledger.phenology_stage,
        "remaining_requirement_kg_ha": remaining,
        "non_actionable_nutrients": non_actionable,
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
        "status": status,
        "action_type": "fertilize" if fertilize else "hold" if blocked else "monitor",
        "recommendation_code": "NUTRIENT_APPLICATION_REQUIRED"
        if fertilize
        else "NUTRIENT_LEDGER_BLOCKED"
        if blocked
        else "NUTRIENT_BALANCE_MONITOR",
        "confidence": confidence,
        "operational_allowed": fertilize,
        "requires_human_approval": fertilize,
        "payload": payload,
        "evidence_digests": sorted(ledger.evidence_digests),
        "constraints": limitations,
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
