"""M5 governed irrigation closed-loop learning and production certification.

The module closes irrigation lineage from recommendation through measured
as-applied truth, water-ledger reconciliation, outcome evidence and a human-
reviewed learning proposal.  It never mutates calibration parameters and never
marks production certified unless every required runtime gate is evidenced.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "irrigation_closed_loop_learning.v1"
PRODUCT_VERSION = "irrigation-closed-loop/1.0.0"
REQUIRED_LINEAGE_DIGESTS = {
    "decision_content_digest",
    "authorization_digest",
    "execution_plan_digest",
    "as_applied_digest",
    "water_ledger_event_digest",
    "outcome_evidence_digest",
}
REQUIRED_PRODUCTION_GATES = {
    "postgres_migrations",
    "tenant_rls_isolation",
    "weather_runtime",
    "soil_runtime",
    "decision_runtime",
    "controller_runtime",
    "actuator_runtime",
    "receipt_verification",
    "outcome_reconciliation",
    "idempotency_replay",
    "fail_safe_recovery",
    "observability_audit",
}


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _utc(value: str | datetime) -> datetime:
    result = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value.lower())
    )


@dataclass(frozen=True)
class IrrigationOutcomeEvidence:
    tenant_id: str
    field_id: str
    season_id: str
    decision_id: str
    execution_plan_id: str
    measured_at: str
    planned_depth_mm: float
    actual_depth_mm: float
    depletion_before_mm: float
    depletion_after_mm: float
    expected_depletion_after_mm: float
    water_use_efficiency_kg_m3: float | None
    energy_kwh: float | None
    stress_days_observed: float | None
    yield_t_ha: float | None
    source_digests: dict[str, str]
    outcome_status: str
    reason_codes: list[str]
    outcome_evidence_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GovernedLearningProposal:
    tenant_id: str
    field_id: str
    season_id: str
    proposal_id: str
    status: str
    review_required: bool
    auto_adjust: bool
    proposed_parameter_changes: list[dict[str, Any]]
    evidence_digest: str
    source_lineage: dict[str, str]
    limitations: list[str]
    proposal_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IrrigationClosedLoopRecord:
    schema_version: str
    product_version: str
    tenant_id: str
    field_id: str
    season_id: str
    decision_id: str
    authorization_id: str
    execution_plan_id: str
    lifecycle_status: str
    verified: bool
    water_ledger_reconciled: bool
    outcome_verified: bool
    learning_eligible: bool
    source_lineage: dict[str, str]
    blocking_reasons: list[str]
    limitations: list[str]
    closed_loop_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProductionCertificationResult:
    environment: str
    release_id: str
    status: str
    production_certified: bool
    certified_at: str | None
    certified_by: str | None
    gate_results: list[dict[str, Any]]
    blocking_gates: list[str]
    evidence_pack_digest: str | None
    certification_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_irrigation_outcome_evidence(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str,
    decision_id: str,
    execution_plan_id: str,
    measured_at: str | datetime,
    planned_depth_mm: float,
    actual_depth_mm: float,
    depletion_before_mm: float,
    depletion_after_mm: float,
    expected_depletion_after_mm: float,
    source_digests: dict[str, str],
    water_use_efficiency_kg_m3: float | None = None,
    energy_kwh: float | None = None,
    stress_days_observed: float | None = None,
    yield_t_ha: float | None = None,
    depletion_tolerance_mm: float = 8.0,
) -> IrrigationOutcomeEvidence:
    numbers = {
        "planned_depth_mm": planned_depth_mm,
        "actual_depth_mm": actual_depth_mm,
        "depletion_before_mm": depletion_before_mm,
        "depletion_after_mm": depletion_after_mm,
        "expected_depletion_after_mm": expected_depletion_after_mm,
        "depletion_tolerance_mm": depletion_tolerance_mm,
    }
    if any(_finite(v) is None or float(v) < 0 for v in numbers.values()):
        raise ValueError("INVALID_IRRIGATION_OUTCOME_MEASUREMENT")
    if not all(
        _is_digest(source_digests.get(name))
        for name in REQUIRED_LINEAGE_DIGESTS - {"outcome_evidence_digest"}
    ):
        raise ValueError("COMPLETE_OUTCOME_SOURCE_LINEAGE_REQUIRED")
    optional = [water_use_efficiency_kg_m3, energy_kwh, stress_days_observed, yield_t_ha]
    if any(v is not None and (_finite(v) is None or float(v) < 0) for v in optional):
        raise ValueError("INVALID_OPTIONAL_OUTCOME_MEASUREMENT")

    reasons: list[str] = []
    delta = abs(float(depletion_after_mm) - float(expected_depletion_after_mm))
    if delta > float(depletion_tolerance_mm):
        reasons.append("DEPLETION_RESPONSE_OUTSIDE_EXPECTED_TOLERANCE")
    if float(actual_depth_mm) <= 0 and float(planned_depth_mm) > 0:
        reasons.append("NO_MEASURED_WATER_APPLIED")
    status = "verified" if not reasons else "degraded"
    payload = {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "season_id": season_id,
        "decision_id": decision_id,
        "execution_plan_id": execution_plan_id,
        "measured_at": _utc(measured_at).isoformat(),
        "planned_depth_mm": float(planned_depth_mm),
        "actual_depth_mm": float(actual_depth_mm),
        "depletion_before_mm": float(depletion_before_mm),
        "depletion_after_mm": float(depletion_after_mm),
        "expected_depletion_after_mm": float(expected_depletion_after_mm),
        "water_use_efficiency_kg_m3": None
        if water_use_efficiency_kg_m3 is None
        else float(water_use_efficiency_kg_m3),
        "energy_kwh": None if energy_kwh is None else float(energy_kwh),
        "stress_days_observed": None
        if stress_days_observed is None
        else float(stress_days_observed),
        "yield_t_ha": None if yield_t_ha is None else float(yield_t_ha),
        "source_digests": dict(sorted(source_digests.items())),
        "outcome_status": status,
        "reason_codes": reasons,
    }
    return IrrigationOutcomeEvidence(**payload, outcome_evidence_digest=_digest(payload))


def build_irrigation_closed_loop_record(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str,
    decision_id: str,
    authorization_id: str,
    execution_plan_id: str,
    decision_status: str,
    approval_status: str,
    execution_status: str,
    as_applied_truth: dict[str, Any],
    water_ledger_event: dict[str, Any],
    outcome_evidence: IrrigationOutcomeEvidence,
) -> IrrigationClosedLoopRecord:
    blocking: list[str] = []
    lineage = {
        "decision_content_digest": as_applied_truth.get("source_lineage", {}).get(
            "decision_content_digest", ""
        ),
        "authorization_digest": water_ledger_event.get("authorization_digest", ""),
        "execution_plan_digest": water_ledger_event.get("execution_plan_digest", ""),
        "as_applied_digest": as_applied_truth.get("as_applied_digest", ""),
        "water_ledger_event_digest": water_ledger_event.get("water_ledger_event_digest", ""),
        "outcome_evidence_digest": outcome_evidence.outcome_evidence_digest,
    }
    if decision_status not in {"approved", "executed", "completed"}:
        blocking.append("APPROVED_DECISION_REQUIRED")
    if approval_status != "approved":
        blocking.append("APPROVAL_REQUIRED")
    if execution_status != "completed":
        blocking.append("COMPLETED_EXECUTION_REQUIRED")
    if as_applied_truth.get("status") != "verified" or not as_applied_truth.get(
        "water_ledger_eligible"
    ):
        blocking.append("VERIFIED_AS_APPLIED_TRUTH_REQUIRED")
    if water_ledger_event.get("status") != "persisted" or not water_ledger_event.get("reconciled"):
        blocking.append("RECONCILED_WATER_LEDGER_EVENT_REQUIRED")
    if outcome_evidence.outcome_status not in {"verified", "degraded"}:
        blocking.append("OUTCOME_EVIDENCE_REQUIRED")
    if not all(_is_digest(lineage[name]) for name in REQUIRED_LINEAGE_DIGESTS):
        blocking.append("COMPLETE_CLOSED_LOOP_LINEAGE_REQUIRED")
    for name, expected in {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "season_id": season_id,
        "decision_id": decision_id,
        "execution_plan_id": execution_plan_id,
    }.items():
        for source in (as_applied_truth, water_ledger_event, outcome_evidence.to_dict()):
            if source.get(name) not in {None, expected}:
                blocking.append(f"CLOSED_LOOP_{name.upper()}_MISMATCH")
                break

    verified = not blocking
    lifecycle = "verified" if verified else "blocked"
    limitations = (
        [] if outcome_evidence.outcome_status == "verified" else list(outcome_evidence.reason_codes)
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "product_version": PRODUCT_VERSION,
        "tenant_id": tenant_id,
        "field_id": field_id,
        "season_id": season_id,
        "decision_id": decision_id,
        "authorization_id": authorization_id,
        "execution_plan_id": execution_plan_id,
        "lifecycle_status": lifecycle,
        "verified": verified,
        "water_ledger_reconciled": water_ledger_event.get("status") == "persisted"
        and bool(water_ledger_event.get("reconciled")),
        "outcome_verified": outcome_evidence.outcome_status == "verified",
        "learning_eligible": verified,
        "source_lineage": lineage,
        "blocking_reasons": sorted(set(blocking)),
        "limitations": limitations,
    }
    return IrrigationClosedLoopRecord(**payload, closed_loop_digest=_digest(payload))


def propose_governed_irrigation_learning(
    *,
    closed_loop: IrrigationClosedLoopRecord,
    outcome_evidence: IrrigationOutcomeEvidence,
    minimum_samples: int,
    sample_count: int,
) -> GovernedLearningProposal:
    limitations: list[str] = []
    changes: list[dict[str, Any]] = []
    if not closed_loop.learning_eligible:
        limitations.append("VERIFIED_CLOSED_LOOP_REQUIRED")
    if sample_count < minimum_samples:
        limitations.append("MINIMUM_FIELD_SAMPLE_COUNT_NOT_MET")
    if outcome_evidence.outcome_status == "degraded":
        deviation = (
            outcome_evidence.depletion_after_mm - outcome_evidence.expected_depletion_after_mm
        )
        if abs(deviation) > 0:
            changes.append(
                {
                    "parameter_family": "root_zone_water_response",
                    "candidate_parameters": [
                        "irrigation_efficiency",
                        "infiltration_loss",
                        "root_depth_m",
                    ],
                    "observed_direction": "less_water_retained"
                    if deviation > 0
                    else "more_water_retained",
                    "evidence_only": True,
                }
            )
    status = (
        "review_ready"
        if not limitations and changes
        else ("monitor" if not limitations else "blocked")
    )
    source_lineage = {
        "closed_loop_digest": closed_loop.closed_loop_digest,
        "outcome_evidence_digest": outcome_evidence.outcome_evidence_digest,
    }
    evidence_digest = _digest({"source_lineage": source_lineage, "sample_count": sample_count})
    proposal_id = f"ilp_{evidence_digest[:20]}"
    payload = {
        "tenant_id": closed_loop.tenant_id,
        "field_id": closed_loop.field_id,
        "season_id": closed_loop.season_id,
        "proposal_id": proposal_id,
        "status": status,
        "review_required": True,
        "auto_adjust": False,
        "proposed_parameter_changes": changes,
        "evidence_digest": evidence_digest,
        "source_lineage": source_lineage,
        "limitations": limitations,
    }
    return GovernedLearningProposal(**payload, proposal_digest=_digest(payload))


def certify_irrigation_production_runtime(
    *,
    environment: str,
    release_id: str,
    gate_results: list[dict[str, Any]],
    evidence_pack_digest: str | None,
    certified_by: str | None = None,
    certified_at: str | datetime | None = None,
) -> ProductionCertificationResult:
    by_name = {str(g.get("gate")): g for g in gate_results}
    blocking: list[str] = []
    normalized: list[dict[str, Any]] = []
    for gate in sorted(REQUIRED_PRODUCTION_GATES):
        value = by_name.get(gate)
        passed = bool(
            value and value.get("passed") is True and _is_digest(value.get("evidence_digest"))
        )
        normalized.append(
            {
                "gate": gate,
                "passed": passed,
                "evidence_digest": value.get("evidence_digest") if value else None,
                "details": value.get("details") if value else "missing",
            }
        )
        if not passed:
            blocking.append(gate)
    if not _is_digest(evidence_pack_digest):
        blocking.append("evidence_pack")
    if environment.lower() != "production":
        blocking.append("production_environment_required")
    certified = not blocking and bool(certified_by) and certified_at is not None
    if not certified_by:
        blocking.append("certified_by")
    if certified_at is None:
        blocking.append("certified_at")
    status = "certified" if certified else "blocked"
    certified_at_text = _utc(certified_at).isoformat() if certified_at is not None else None
    payload = {
        "environment": environment,
        "release_id": release_id,
        "status": status,
        "production_certified": certified,
        "certified_at": certified_at_text,
        "certified_by": certified_by,
        "gate_results": normalized,
        "blocking_gates": sorted(set(blocking)),
        "evidence_pack_digest": evidence_pack_digest if _is_digest(evidence_pack_digest) else None,
    }
    return ProductionCertificationResult(**payload, certification_digest=_digest(payload))
