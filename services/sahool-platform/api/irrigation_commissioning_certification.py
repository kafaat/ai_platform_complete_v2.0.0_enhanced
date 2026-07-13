"""M2.10 irrigation commissioning and certification boundary.

Turns field installation evidence and witnessed commissioning tests into a
versioned, expiring certification snapshot.  The module never dispatches a
command.  It only decides whether an otherwise verified irrigation capability
graph may be treated as executable by downstream governed decision flows.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "irrigation_commissioning_certification.v1"
PRODUCT_VERSION = "irrigation-commissioning/1.0.0"
REQUIRED_EVIDENCE_TYPES = {
    "installation_identity",
    "pump_flow_test",
    "pressure_test",
    "controller_handshake",
    "safety_interlock_test",
    "energy_system_test",
    "signed_acceptance",
}
REQUIRED_SAFETY_CHECKS = {
    "emergency_stop",
    "dry_run_protection",
    "overpressure_protection",
    "loss_of_communication_safe_state",
    "manual_override",
}
ALLOWED_EVIDENCE_STATUS = {"verified", "rejected", "superseded"}
ALLOWED_CERTIFICATION_STATUS = {
    "draft",
    "in_review",
    "certified",
    "expired",
    "revoked",
    "superseded",
}


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


@dataclass(frozen=True)
class CommissioningEvidence:
    tenant_id: str
    project_id: str
    field_id: str
    machine_id: str
    evidence_type: str
    status: str
    observed_at: str
    captured_by: str
    source_uri: str | None
    source_hash: str
    values: dict[str, Any]
    witness_id: str | None
    evidence_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IrrigationCommissioningCertification:
    schema_version: str
    product_version: str
    tenant_id: str
    project_id: str
    field_id: str
    season_id: str
    machine_id: str
    controller_id: str
    energy_system_id: str
    status: str
    operational_eligible: bool
    certified_at: str | None
    valid_until: str | None
    certification_scope: list[str]
    measured_flow_lps: float | None
    measured_terminal_pressure_bar: float | None
    measured_power_kw: float | None
    controller_handshake_digest: str | None
    irrigation_capability_digest: str
    evidence_digests: list[str]
    safety_checks: dict[str, bool]
    signed_by: str | None
    reviewed_by: str | None
    limitations: list[str]
    blocking_reasons: list[str]
    certification_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_commissioning_evidence(
    *,
    tenant_id: str,
    project_id: str,
    field_id: str,
    machine_id: str,
    evidence_type: str,
    status: str,
    observed_at: str | datetime,
    captured_by: str,
    source_hash: str,
    values: dict[str, Any],
    source_uri: str | None = None,
    witness_id: str | None = None,
) -> CommissioningEvidence:
    if evidence_type not in REQUIRED_EVIDENCE_TYPES:
        raise ValueError("UNSUPPORTED_COMMISSIONING_EVIDENCE_TYPE")
    if status not in ALLOWED_EVIDENCE_STATUS:
        raise ValueError("INVALID_COMMISSIONING_EVIDENCE_STATUS")
    if not captured_by:
        raise ValueError("EVIDENCE_CAPTURED_BY_REQUIRED")
    if not isinstance(source_hash, str) or len(source_hash) != 64:
        raise ValueError("EVIDENCE_SOURCE_SHA256_REQUIRED")
    normalized = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "field_id": field_id,
        "machine_id": machine_id,
        "evidence_type": evidence_type,
        "status": status,
        "observed_at": _utc(observed_at).isoformat(),
        "captured_by": captured_by,
        "source_uri": source_uri,
        "source_hash": source_hash,
        "values": dict(values or {}),
        "witness_id": witness_id,
    }
    return CommissioningEvidence(**normalized, evidence_digest=_digest(normalized))


def build_irrigation_commissioning_certification(
    *,
    tenant_id: str,
    project_id: str,
    field_id: str,
    season_id: str,
    machine_id: str,
    controller_id: str,
    energy_system_id: str,
    irrigation_capability_digest: str,
    evidence: list[CommissioningEvidence],
    safety_checks: dict[str, bool],
    certification_status: str,
    now: str | datetime,
    certified_at: str | datetime | None,
    valid_until: str | datetime | None,
    signed_by: str | None,
    reviewed_by: str | None,
    certification_scope: list[str] | None = None,
    maximum_evidence_age_days: int = 365,
    minimum_flow_ratio: float = 0.90,
    minimum_pressure_ratio: float = 0.90,
    design_flow_lps: float | None = None,
    design_terminal_pressure_bar: float | None = None,
    maximum_power_kw: float | None = None,
) -> IrrigationCommissioningCertification:
    """Build a fail-closed commissioning certificate.

    Certified status is necessary but not sufficient.  Every required evidence
    class must be verified, current, identity-bound and internally consistent.
    """
    if certification_status not in ALLOWED_CERTIFICATION_STATUS:
        raise ValueError("INVALID_CERTIFICATION_STATUS")
    if not isinstance(irrigation_capability_digest, str) or len(irrigation_capability_digest) != 64:
        raise ValueError("IRRIGATION_CAPABILITY_DIGEST_REQUIRED")
    current = _utc(now)
    blockers: list[str] = []
    limitations: list[str] = []

    by_type: dict[str, CommissioningEvidence] = {}
    for item in evidence:
        if (
            item.tenant_id != tenant_id
            or item.project_id != project_id
            or item.field_id != field_id
            or item.machine_id != machine_id
        ):
            blockers.append("COMMISSIONING_EVIDENCE_IDENTITY_MISMATCH")
            continue
        previous = by_type.get(item.evidence_type)
        if previous is None or _utc(item.observed_at) > _utc(previous.observed_at):
            by_type[item.evidence_type] = item

    for evidence_type in sorted(REQUIRED_EVIDENCE_TYPES):
        item = by_type.get(evidence_type)
        if item is None:
            blockers.append(f"{evidence_type.upper()}_EVIDENCE_REQUIRED")
            continue
        if item.status != "verified":
            blockers.append(f"{evidence_type.upper()}_EVIDENCE_NOT_VERIFIED")
        age_days = (current - _utc(item.observed_at)).total_seconds() / 86400.0
        if age_days < 0:
            blockers.append(f"{evidence_type.upper()}_EVIDENCE_IN_FUTURE")
        elif age_days > maximum_evidence_age_days:
            blockers.append(f"{evidence_type.upper()}_EVIDENCE_STALE")

    normalized_checks = {str(k): bool(v) for k, v in sorted((safety_checks or {}).items())}
    for check in sorted(REQUIRED_SAFETY_CHECKS):
        if not normalized_checks.get(check):
            blockers.append(f"SAFETY_CHECK_{check.upper()}_REQUIRED")

    if certification_status != "certified":
        blockers.append("CERTIFIED_COMMISSIONING_REQUIRED")
    certified = _utc(certified_at) if certified_at is not None else None
    expires = _utc(valid_until) if valid_until is not None else None
    if certified is None:
        blockers.append("CERTIFIED_AT_REQUIRED")
    elif certified > current:
        blockers.append("CERTIFIED_AT_IN_FUTURE")
    if expires is None:
        blockers.append("CERTIFICATION_EXPIRY_REQUIRED")
    elif expires <= current:
        blockers.append("COMMISSIONING_CERTIFICATION_EXPIRED")
    elif certified is not None and expires <= certified:
        blockers.append("CERTIFICATION_VALIDITY_WINDOW_INVALID")
    if not signed_by:
        blockers.append("COMMISSIONING_SIGNATURE_REQUIRED")
    if not reviewed_by:
        blockers.append("INDEPENDENT_REVIEW_REQUIRED")
    if signed_by and reviewed_by and signed_by == reviewed_by:
        blockers.append("INDEPENDENT_REVIEWER_MUST_DIFFER")

    flow_evidence = by_type.get("pump_flow_test")
    pressure_evidence = by_type.get("pressure_test")
    energy_evidence = by_type.get("energy_system_test")
    controller_evidence = by_type.get("controller_handshake")
    measured_flow = _finite(
        (flow_evidence.values if flow_evidence else {}).get("measured_flow_lps")
    )
    measured_pressure = _finite(
        (pressure_evidence.values if pressure_evidence else {}).get(
            "measured_terminal_pressure_bar"
        )
    )
    measured_power = _finite(
        (energy_evidence.values if energy_evidence else {}).get("measured_power_kw")
    )
    handshake_digest = (controller_evidence.values if controller_evidence else {}).get(
        "handshake_digest"
    )

    if measured_flow is None or measured_flow <= 0:
        blockers.append("MEASURED_FLOW_REQUIRED")
    if design_flow_lps is not None:
        design_flow = _finite(design_flow_lps)
        if design_flow is None or design_flow <= 0:
            blockers.append("DESIGN_FLOW_INVALID")
        elif measured_flow is not None and measured_flow < design_flow * minimum_flow_ratio:
            blockers.append("COMMISSIONED_FLOW_BELOW_ACCEPTANCE_THRESHOLD")

    if measured_pressure is None or measured_pressure <= 0:
        blockers.append("MEASURED_TERMINAL_PRESSURE_REQUIRED")
    if design_terminal_pressure_bar is not None:
        design_pressure = _finite(design_terminal_pressure_bar)
        if design_pressure is None or design_pressure <= 0:
            blockers.append("DESIGN_PRESSURE_INVALID")
        elif (
            measured_pressure is not None
            and measured_pressure < design_pressure * minimum_pressure_ratio
        ):
            blockers.append("COMMISSIONED_PRESSURE_BELOW_ACCEPTANCE_THRESHOLD")

    if measured_power is None or measured_power <= 0:
        blockers.append("MEASURED_POWER_REQUIRED")
    if maximum_power_kw is not None:
        power_limit = _finite(maximum_power_kw)
        if power_limit is None or power_limit <= 0:
            blockers.append("MAXIMUM_POWER_INVALID")
        elif measured_power is not None and measured_power > power_limit:
            blockers.append("COMMISSIONED_POWER_EXCEEDS_CERTIFIED_LIMIT")

    if not isinstance(handshake_digest, str) or len(handshake_digest) != 64:
        blockers.append("CERTIFIED_CONTROLLER_HANDSHAKE_DIGEST_REQUIRED")

    if certification_status in {"revoked", "expired", "superseded"}:
        blockers.append(f"COMMISSIONING_CERTIFICATION_{certification_status.upper()}")

    evidence_digests = sorted(item.evidence_digest for item in by_type.values())
    scope = sorted(set(certification_scope or ["irrigation_execution"]))
    blockers = sorted(set(blockers))
    eligible = not blockers
    digest_payload = {
        "schema_version": SCHEMA_VERSION,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "field_id": field_id,
        "season_id": season_id,
        "machine_id": machine_id,
        "controller_id": controller_id,
        "energy_system_id": energy_system_id,
        "irrigation_capability_digest": irrigation_capability_digest,
        "certification_status": certification_status,
        "certified_at": certified.isoformat() if certified else None,
        "valid_until": expires.isoformat() if expires else None,
        "scope": scope,
        "evidence_digests": evidence_digests,
        "safety_checks": normalized_checks,
        "signed_by": signed_by,
        "reviewed_by": reviewed_by,
        "measured_flow_lps": measured_flow,
        "measured_terminal_pressure_bar": measured_pressure,
        "measured_power_kw": measured_power,
        "controller_handshake_digest": handshake_digest,
        "blocking_reasons": blockers,
    }
    return IrrigationCommissioningCertification(
        schema_version=SCHEMA_VERSION,
        product_version=PRODUCT_VERSION,
        tenant_id=tenant_id,
        project_id=project_id,
        field_id=field_id,
        season_id=season_id,
        machine_id=machine_id,
        controller_id=controller_id,
        energy_system_id=energy_system_id,
        status="certified" if eligible else "blocked",
        operational_eligible=eligible,
        certified_at=certified.isoformat() if certified else None,
        valid_until=expires.isoformat() if expires else None,
        certification_scope=scope,
        measured_flow_lps=measured_flow,
        measured_terminal_pressure_bar=measured_pressure,
        measured_power_kw=measured_power,
        controller_handshake_digest=handshake_digest if isinstance(handshake_digest, str) else None,
        irrigation_capability_digest=irrigation_capability_digest,
        evidence_digests=evidence_digests,
        safety_checks=normalized_checks,
        signed_by=signed_by,
        reviewed_by=reviewed_by,
        limitations=limitations,
        blocking_reasons=blockers,
        certification_digest=_digest(digest_payload),
    )


def apply_commissioning_executability_gate(
    *,
    capability_graph: dict[str, Any] | Any,
    certification: IrrigationCommissioningCertification,
) -> dict[str, Any]:
    """Bind certification to one immutable capability graph snapshot."""
    graph = (
        capability_graph.to_dict()
        if hasattr(capability_graph, "to_dict")
        else dict(capability_graph or {})
    )
    blockers = list(graph.get("blocking_reasons") or [])
    graph_digest = graph.get("capability_digest")
    identities = {
        "tenant_id": graph.get("tenant_id"),
        "project_id": graph.get("project_id"),
        "field_id": graph.get("field_id"),
        "season_id": graph.get("season_id"),
        "machine_id": graph.get("machine_id"),
        "controller_id": graph.get("controller_id"),
        "energy_system_id": graph.get("energy_system_id"),
    }
    for name, graph_value in identities.items():
        cert_value = getattr(certification, name)
        if str(graph_value or "") != str(cert_value or ""):
            blockers.append(f"COMMISSIONING_GRAPH_{name.upper()}_MISMATCH")
    if graph_digest != certification.irrigation_capability_digest:
        blockers.append("COMMISSIONING_CAPABILITY_DIGEST_MISMATCH")
    if graph.get("status") != "verified" or not graph.get("operational_eligible"):
        blockers.append("IRRIGATION_CAPABILITY_GRAPH_NOT_OPERATIONAL")
    if not certification.operational_eligible or certification.status != "certified":
        blockers.extend(
            certification.blocking_reasons or ["COMMISSIONING_CERTIFICATION_NOT_OPERATIONAL"]
        )
    blockers = sorted(set(str(item) for item in blockers))
    executable = not blockers
    payload = {
        "schema_version": "irrigation_executability_gate.v1",
        "status": "executable" if executable else "blocked",
        "execution_allowed": executable,
        "tenant_id": certification.tenant_id,
        "project_id": certification.project_id,
        "field_id": certification.field_id,
        "season_id": certification.season_id,
        "machine_id": certification.machine_id,
        "controller_id": certification.controller_id,
        "energy_system_id": certification.energy_system_id,
        "irrigation_capability_digest": graph_digest,
        "commissioning_certification_digest": certification.certification_digest,
        "valid_until": certification.valid_until,
        "blocking_reasons": blockers,
    }
    payload["executability_digest"] = _digest(payload)
    return payload
