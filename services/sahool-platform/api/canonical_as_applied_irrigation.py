"""M2.11 canonical as-applied irrigation truth.

Fuses one authorized irrigation plan with controller receipts and measured
flow/pressure/runtime/position observations. The module is append-only in
intent, never dispatches a command, and only emits a verified as-applied truth
when identity, lineage, telemetry freshness, sequence integrity and coverage
checks all pass.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "canonical_as_applied_irrigation.v1"
PRODUCT_VERSION = "as-applied-irrigation/1.0.0"
REQUIRED_OBSERVATION_TYPES = {"flow", "pressure", "runtime", "position"}
TERMINAL_RECEIPT_STATES = {"completed", "stopped", "failed", "cancelled"}


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _utc(value: str | datetime) -> datetime:
    dt = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


@dataclass(frozen=True)
class AuthorizedIrrigationPlan:
    tenant_id: str
    field_id: str
    season_id: str
    machine_id: str
    controller_id: str
    decision_id: str
    authorization_id: str
    execution_plan_id: str
    planned_start_at: str
    planned_end_at: str
    planned_depth_mm: float
    planned_volume_m3: float
    planned_area_ha: float
    irrigation_capability_digest: str
    commissioning_certification_digest: str
    decision_content_digest: str
    plan_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IrrigationExecutionReceipt:
    tenant_id: str
    field_id: str
    machine_id: str
    controller_id: str
    execution_plan_id: str
    receipt_id: str
    state: str
    sequence_number: int
    observed_at: str
    controller_command_digest: str
    payload_digest: str
    receipt_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AsAppliedObservation:
    tenant_id: str
    field_id: str
    machine_id: str
    controller_id: str
    execution_plan_id: str
    observation_type: str
    sequence_number: int
    observed_at: str
    value: float
    unit: str
    source_message_id: str
    payload_digest: str
    observation_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalAsAppliedIrrigationTruth:
    schema_version: str
    product_version: str
    tenant_id: str
    field_id: str
    season_id: str
    machine_id: str
    controller_id: str
    decision_id: str
    authorization_id: str
    execution_plan_id: str
    status: str
    verification_status: str
    actual_start_at: str | None
    actual_end_at: str | None
    actual_runtime_minutes: float | None
    actual_volume_m3: float | None
    actual_depth_mm: float | None
    actual_area_ha: float | None
    mean_flow_lps: float | None
    mean_pressure_bar: float | None
    position_coverage_percent: float | None
    planned_volume_m3: float
    planned_depth_mm: float
    volume_variance_m3: float | None
    volume_variance_percent: float | None
    depth_variance_mm: float | None
    depth_variance_percent: float | None
    completion_ratio: float | None
    water_ledger_eligible: bool
    source_receipt_digests: list[str]
    source_observation_digests: list[str]
    source_lineage: dict[str, str]
    blocking_reasons: list[str]
    limitations: list[str]
    as_applied_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_authorized_irrigation_plan(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str,
    machine_id: str,
    controller_id: str,
    decision_id: str,
    authorization_id: str,
    execution_plan_id: str,
    planned_start_at: str | datetime,
    planned_end_at: str | datetime,
    planned_depth_mm: float,
    planned_volume_m3: float,
    planned_area_ha: float,
    irrigation_capability_digest: str,
    commissioning_certification_digest: str,
    decision_content_digest: str,
) -> AuthorizedIrrigationPlan:
    start, end = _utc(planned_start_at), _utc(planned_end_at)
    if end <= start:
        raise ValueError("PLANNED_TIME_WINDOW_INVALID")
    values = [planned_depth_mm, planned_volume_m3, planned_area_ha]
    if any(_finite(v) is None or float(v) <= 0 for v in values):
        raise ValueError("PLANNED_IRRIGATION_QUANTITY_INVALID")
    for name, value in {
        "IRRIGATION_CAPABILITY_DIGEST": irrigation_capability_digest,
        "COMMISSIONING_CERTIFICATION_DIGEST": commissioning_certification_digest,
        "DECISION_CONTENT_DIGEST": decision_content_digest,
    }.items():
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"{name}_REQUIRED")
    payload = {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "season_id": season_id,
        "machine_id": machine_id,
        "controller_id": controller_id,
        "decision_id": decision_id,
        "authorization_id": authorization_id,
        "execution_plan_id": execution_plan_id,
        "planned_start_at": start.isoformat(),
        "planned_end_at": end.isoformat(),
        "planned_depth_mm": float(planned_depth_mm),
        "planned_volume_m3": float(planned_volume_m3),
        "planned_area_ha": float(planned_area_ha),
        "irrigation_capability_digest": irrigation_capability_digest,
        "commissioning_certification_digest": commissioning_certification_digest,
        "decision_content_digest": decision_content_digest,
    }
    return AuthorizedIrrigationPlan(**payload, plan_digest=_digest(payload))


def build_execution_receipt(
    *,
    tenant_id: str,
    field_id: str,
    machine_id: str,
    controller_id: str,
    execution_plan_id: str,
    receipt_id: str,
    state: str,
    sequence_number: int,
    observed_at: str | datetime,
    controller_command_digest: str,
    payload_digest: str,
) -> IrrigationExecutionReceipt:
    if state not in {"accepted", "running", *TERMINAL_RECEIPT_STATES}:
        raise ValueError("INVALID_EXECUTION_RECEIPT_STATE")
    if sequence_number < 0:
        raise ValueError("INVALID_RECEIPT_SEQUENCE")
    if len(controller_command_digest) != 64 or len(payload_digest) != 64:
        raise ValueError("RECEIPT_SOURCE_DIGEST_REQUIRED")
    payload = {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "machine_id": machine_id,
        "controller_id": controller_id,
        "execution_plan_id": execution_plan_id,
        "receipt_id": receipt_id,
        "state": state,
        "sequence_number": sequence_number,
        "observed_at": _utc(observed_at).isoformat(),
        "controller_command_digest": controller_command_digest,
        "payload_digest": payload_digest,
    }
    return IrrigationExecutionReceipt(**payload, receipt_digest=_digest(payload))


def build_as_applied_observation(
    *,
    tenant_id: str,
    field_id: str,
    machine_id: str,
    controller_id: str,
    execution_plan_id: str,
    observation_type: str,
    sequence_number: int,
    observed_at: str | datetime,
    value: float,
    unit: str,
    source_message_id: str,
    payload_digest: str,
) -> AsAppliedObservation:
    if observation_type not in REQUIRED_OBSERVATION_TYPES:
        raise ValueError("UNSUPPORTED_AS_APPLIED_OBSERVATION_TYPE")
    number = _finite(value)
    if number is None or number < 0:
        raise ValueError("INVALID_AS_APPLIED_OBSERVATION_VALUE")
    if sequence_number < 0 or not source_message_id:
        raise ValueError("INVALID_AS_APPLIED_OBSERVATION_IDENTITY")
    if len(payload_digest) != 64:
        raise ValueError("OBSERVATION_PAYLOAD_DIGEST_REQUIRED")
    expected_units = {"flow": "lps", "pressure": "bar", "runtime": "minutes", "position": "percent"}
    if unit != expected_units[observation_type]:
        raise ValueError("AS_APPLIED_OBSERVATION_UNIT_MISMATCH")
    if observation_type == "position" and number > 100:
        raise ValueError("POSITION_PERCENT_OUT_OF_RANGE")
    payload = {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "machine_id": machine_id,
        "controller_id": controller_id,
        "execution_plan_id": execution_plan_id,
        "observation_type": observation_type,
        "sequence_number": sequence_number,
        "observed_at": _utc(observed_at).isoformat(),
        "value": number,
        "unit": unit,
        "source_message_id": source_message_id,
        "payload_digest": payload_digest,
    }
    return AsAppliedObservation(**payload, observation_digest=_digest(payload))


def build_canonical_as_applied_irrigation_truth(
    *,
    plan: AuthorizedIrrigationPlan,
    receipts: list[IrrigationExecutionReceipt],
    observations: list[AsAppliedObservation],
    now: str | datetime,
    maximum_telemetry_age_minutes: int = 30,
    maximum_volume_variance_percent: float = 15.0,
    minimum_position_coverage_percent: float = 90.0,
) -> CanonicalAsAppliedIrrigationTruth:
    current = _utc(now)
    blockers: list[str] = []
    limitations: list[str] = []

    def identity_matches(item: Any) -> bool:
        return all(
            getattr(item, k) == getattr(plan, k)
            for k in ("tenant_id", "field_id", "machine_id", "controller_id", "execution_plan_id")
        )

    valid_receipts = [r for r in receipts if identity_matches(r)]
    if len(valid_receipts) != len(receipts):
        blockers.append("EXECUTION_RECEIPT_IDENTITY_MISMATCH")
    valid_observations = [o for o in observations if identity_matches(o)]
    if len(valid_observations) != len(observations):
        blockers.append("AS_APPLIED_OBSERVATION_IDENTITY_MISMATCH")

    for items, prefix in ((valid_receipts, "RECEIPT"), (valid_observations, "OBSERVATION")):
        ordered = sorted(items, key=lambda x: (x.sequence_number, _utc(x.observed_at)))
        seen_seq: set[int] = set()
        seen_time: datetime | None = None
        for item in ordered:
            t = _utc(item.observed_at)
            if item.sequence_number in seen_seq:
                blockers.append(f"{prefix}_SEQUENCE_REPLAY")
            if seen_time is not None and t <= seen_time:
                blockers.append(f"{prefix}_TIMESTAMP_REPLAY_OR_OUT_OF_ORDER")
            seen_seq.add(item.sequence_number)
            seen_time = t
            age = (current - t).total_seconds() / 60.0
            if age < 0:
                blockers.append(f"{prefix}_IN_FUTURE")

    if not valid_receipts:
        blockers.append("EXECUTION_RECEIPT_REQUIRED")
    terminal = [r for r in valid_receipts if r.state in TERMINAL_RECEIPT_STATES]
    if not terminal:
        blockers.append("TERMINAL_EXECUTION_RECEIPT_REQUIRED")
    final_receipt = max(terminal, key=lambda r: r.sequence_number) if terminal else None
    if final_receipt and final_receipt.state != "completed":
        blockers.append(f"EXECUTION_{final_receipt.state.upper()}")

    by_type: dict[str, list[AsAppliedObservation]] = {k: [] for k in REQUIRED_OBSERVATION_TYPES}
    for item in valid_observations:
        by_type[item.observation_type].append(item)
    for kind in sorted(REQUIRED_OBSERVATION_TYPES):
        if not by_type[kind]:
            blockers.append(f"AS_APPLIED_{kind.upper()}_OBSERVATION_REQUIRED")
    if valid_observations:
        latest = max(_utc(o.observed_at) for o in valid_observations)
        if (current - latest).total_seconds() / 60.0 > maximum_telemetry_age_minutes:
            blockers.append("AS_APPLIED_TELEMETRY_STALE")

    flow_values = [o.value for o in by_type["flow"]]
    pressure_values = [o.value for o in by_type["pressure"]]
    runtime_values = [o.value for o in by_type["runtime"]]
    position_values = [o.value for o in by_type["position"]]
    mean_flow = sum(flow_values) / len(flow_values) if flow_values else None
    mean_pressure = sum(pressure_values) / len(pressure_values) if pressure_values else None
    runtime_minutes = max(runtime_values) if runtime_values else None
    coverage = (max(position_values) - min(position_values)) if len(position_values) >= 2 else None
    if coverage is not None and coverage < minimum_position_coverage_percent:
        blockers.append("POSITION_COVERAGE_BELOW_ACCEPTANCE_THRESHOLD")

    actual_volume = (
        mean_flow * runtime_minutes * 0.06
        if mean_flow is not None and runtime_minutes is not None
        else None
    )
    actual_area = plan.planned_area_ha * (coverage / 100.0) if coverage is not None else None
    actual_depth = (
        actual_volume / (actual_area * 10.0)
        if actual_volume is not None and actual_area and actual_area > 0
        else None
    )
    volume_variance = actual_volume - plan.planned_volume_m3 if actual_volume is not None else None
    volume_variance_pct = (
        100.0 * volume_variance / plan.planned_volume_m3 if volume_variance is not None else None
    )
    depth_variance = actual_depth - plan.planned_depth_mm if actual_depth is not None else None
    depth_variance_pct = (
        100.0 * depth_variance / plan.planned_depth_mm if depth_variance is not None else None
    )
    completion_ratio = actual_volume / plan.planned_volume_m3 if actual_volume is not None else None
    if (
        volume_variance_pct is not None
        and abs(volume_variance_pct) > maximum_volume_variance_percent
    ):
        blockers.append("AS_APPLIED_VOLUME_VARIANCE_EXCEEDS_TOLERANCE")

    actual_start = min(
        (_utc(r.observed_at) for r in valid_receipts if r.state in {"accepted", "running"}),
        default=None,
    )
    actual_end = _utc(final_receipt.observed_at) if final_receipt else None
    blockers = sorted(set(blockers))
    verified = not blockers
    source_lineage = {
        "plan_digest": plan.plan_digest,
        "decision_content_digest": plan.decision_content_digest,
        "irrigation_capability_digest": plan.irrigation_capability_digest,
        "commissioning_certification_digest": plan.commissioning_certification_digest,
        "authorization_id": plan.authorization_id,
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": plan.tenant_id,
        "field_id": plan.field_id,
        "season_id": plan.season_id,
        "machine_id": plan.machine_id,
        "controller_id": plan.controller_id,
        "decision_id": plan.decision_id,
        "authorization_id": plan.authorization_id,
        "execution_plan_id": plan.execution_plan_id,
        "actual_start_at": actual_start.isoformat() if actual_start else None,
        "actual_end_at": actual_end.isoformat() if actual_end else None,
        "actual_runtime_minutes": runtime_minutes,
        "actual_volume_m3": actual_volume,
        "actual_depth_mm": actual_depth,
        "actual_area_ha": actual_area,
        "mean_flow_lps": mean_flow,
        "mean_pressure_bar": mean_pressure,
        "position_coverage_percent": coverage,
        "planned_volume_m3": plan.planned_volume_m3,
        "planned_depth_mm": plan.planned_depth_mm,
        "volume_variance_m3": volume_variance,
        "volume_variance_percent": volume_variance_pct,
        "depth_variance_mm": depth_variance,
        "depth_variance_percent": depth_variance_pct,
        "completion_ratio": completion_ratio,
        "source_receipt_digests": sorted(r.receipt_digest for r in valid_receipts),
        "source_observation_digests": sorted(o.observation_digest for o in valid_observations),
        "source_lineage": source_lineage,
        "blocking_reasons": blockers,
    }
    return CanonicalAsAppliedIrrigationTruth(
        schema_version=SCHEMA_VERSION,
        product_version=PRODUCT_VERSION,
        tenant_id=plan.tenant_id,
        field_id=plan.field_id,
        season_id=plan.season_id,
        machine_id=plan.machine_id,
        controller_id=plan.controller_id,
        decision_id=plan.decision_id,
        authorization_id=plan.authorization_id,
        execution_plan_id=plan.execution_plan_id,
        status="verified" if verified else "blocked",
        verification_status="verified" if verified else "unverified",
        actual_start_at=payload["actual_start_at"],
        actual_end_at=payload["actual_end_at"],
        actual_runtime_minutes=runtime_minutes,
        actual_volume_m3=actual_volume,
        actual_depth_mm=actual_depth,
        actual_area_ha=actual_area,
        mean_flow_lps=mean_flow,
        mean_pressure_bar=mean_pressure,
        position_coverage_percent=coverage,
        planned_volume_m3=plan.planned_volume_m3,
        planned_depth_mm=plan.planned_depth_mm,
        volume_variance_m3=volume_variance,
        volume_variance_percent=volume_variance_pct,
        depth_variance_mm=depth_variance,
        depth_variance_percent=depth_variance_pct,
        completion_ratio=completion_ratio,
        water_ledger_eligible=verified,
        source_receipt_digests=payload["source_receipt_digests"],
        source_observation_digests=payload["source_observation_digests"],
        source_lineage=source_lineage,
        blocking_reasons=blockers,
        limitations=limitations,
        as_applied_digest=_digest(payload),
    )


def as_applied_truth_to_water_ledger_event(
    truth: CanonicalAsAppliedIrrigationTruth,
) -> dict[str, Any]:
    """Return a non-persisting ledger event only for verified measured water."""
    if truth.status != "verified" or not truth.water_ledger_eligible:
        return {"status": "blocked", "blocking_reasons": truth.blocking_reasons}
    payload = {
        "event_type": "irrigation_as_applied.v1",
        "tenant_id": truth.tenant_id,
        "field_id": truth.field_id,
        "season_id": truth.season_id,
        "execution_plan_id": truth.execution_plan_id,
        "decision_id": truth.decision_id,
        "authorization_id": truth.authorization_id,
        "applied_volume_m3": truth.actual_volume_m3,
        "applied_depth_mm": truth.actual_depth_mm,
        "observed_at": truth.actual_end_at,
        "as_applied_digest": truth.as_applied_digest,
        "source": "measured_as_applied_truth",
    }
    payload["ledger_event_digest"] = _digest(payload)
    return {"status": "available", **payload}
