"""IRR-X1.1 digital commissioning runtime.

Builds a legal, versioned commissioning certificate from field tests and
produces the central execution-authorization gate. The module is vendor-neutral
and never dispatches controller commands.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CommissioningState(StrEnum):
    DRAFT = "draft"
    TESTING = "testing"
    PENDING_REVIEW = "pending_review"
    PASS = "pass"
    DEGRADED = "degraded"
    FAIL = "fail"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class CommissioningTestOutcome(StrEnum):
    PASS = "pass"
    DEGRADED = "degraded"
    FAIL = "fail"


FINAL_STATES = {
    CommissioningState.PASS,
    CommissioningState.DEGRADED,
    CommissioningState.FAIL,
    CommissioningState.EXPIRED,
    CommissioningState.REVOKED,
    CommissioningState.SUPERSEDED,
}

ALLOWED_TRANSITIONS: dict[CommissioningState, set[CommissioningState]] = {
    CommissioningState.DRAFT: {CommissioningState.TESTING, CommissioningState.REVOKED},
    CommissioningState.TESTING: {
        CommissioningState.PENDING_REVIEW,
        CommissioningState.DRAFT,
        CommissioningState.REVOKED,
    },
    CommissioningState.PENDING_REVIEW: {
        CommissioningState.PASS,
        CommissioningState.DEGRADED,
        CommissioningState.FAIL,
        CommissioningState.TESTING,
        CommissioningState.REVOKED,
    },
    CommissioningState.PASS: {
        CommissioningState.EXPIRED,
        CommissioningState.REVOKED,
        CommissioningState.SUPERSEDED,
    },
    CommissioningState.DEGRADED: {
        CommissioningState.EXPIRED,
        CommissioningState.REVOKED,
        CommissioningState.SUPERSEDED,
    },
    CommissioningState.FAIL: {CommissioningState.SUPERSEDED, CommissioningState.REVOKED},
    CommissioningState.EXPIRED: {CommissioningState.SUPERSEDED},
    CommissioningState.REVOKED: {CommissioningState.SUPERSEDED},
    CommissioningState.SUPERSEDED: set(),
}

REQUIRED_TEST_TYPES = {
    "pump_curve",
    "operating_pressure",
    "actual_flow",
    "pressure_stability",
    "leak_and_pressure_collapse",
    "dry_run_protection",
    "voltage_drop",
    "frequency_stability",
    "essential_sensors",
    "emergency_stop",
}

AUTOMATION_REQUIRED_TEST_TYPES = REQUIRED_TEST_TYPES | {
    "controller_connectivity",
    "valve_state",
}


class CommissioningTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    test_id: str
    test_type: str
    outcome: CommissioningTestOutcome
    tested_at: datetime
    measured: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    design: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    tolerances: dict[str, float] = Field(default_factory=dict)
    evidence_digests: list[str] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> CommissioningTest:
        for digest in self.evidence_digests:
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("INVALID_EVIDENCE_DIGEST")
        return self


class CommissioningCertificateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    certificate_id: str
    tenant_id: str
    field_id: str
    season_id: str | None = None
    system_id: str
    machine_id: str | None = None
    pump_id: str | None = None
    controller_id: str | None = None
    specification_version: str
    specification_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_graph_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    commissioning_version: int = Field(ge=1)
    tested_at: datetime
    valid_until: datetime
    tests: list[CommissioningTest]
    safety_interlocks: dict[str, bool] = Field(default_factory=dict)
    execution_limits: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    requested_execution_modes: list[str] = Field(default_factory=list)
    issued_by: str
    reviewed_by: str
    supersedes_certificate_id: str | None = None

    @model_validator(mode="after")
    def validate_window_and_review(self) -> CommissioningCertificateInput:
        tested_at = self.tested_at if self.tested_at.tzinfo else self.tested_at.replace(tzinfo=UTC)
        valid_until = (
            self.valid_until if self.valid_until.tzinfo else self.valid_until.replace(tzinfo=UTC)
        )
        if valid_until <= tested_at:
            raise ValueError("COMMISSIONING_VALIDITY_WINDOW_INVALID")
        if self.issued_by == self.reviewed_by:
            raise ValueError("INDEPENDENT_REVIEW_REQUIRED")
        return self


class CommissioningCertificate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    certificate_id: str
    tenant_id: str
    field_id: str
    season_id: str | None
    system_id: str
    machine_id: str | None
    pump_id: str | None
    controller_id: str | None
    commissioning_version: int
    status: CommissioningState
    tested_at: datetime
    valid_until: datetime
    flow_curve_digest: str | None
    pressure_curve_digest: str | None
    power_curve_digest: str | None
    specification_digest: str
    capability_graph_digest: str
    safety_interlocks: dict[str, bool]
    execution_limits: dict[str, float | int | str | bool | None]
    permitted_execution_modes: list[str]
    blocking_failures: list[str]
    warnings: list[str]
    tests: list[CommissioningTest]
    issued_by: str
    reviewed_by: str
    supersedes_certificate_id: str | None
    certificate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExecutionAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_allowed: bool
    manual_execution_allowed: bool
    requested_mode: str
    certificate_id: str | None
    certificate_digest: str | None
    blocking_reasons: list[str]
    authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def transition_commissioning_state(
    current: CommissioningState, target: CommissioningState
) -> CommissioningState:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"INVALID_COMMISSIONING_TRANSITION:{current.value}->{target.value}")
    return target


def build_commissioning_certificate(
    payload: CommissioningCertificateInput,
    *,
    now: datetime | None = None,
) -> CommissioningCertificate:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)

    latest_by_type: dict[str, CommissioningTest] = {}
    for test in payload.tests:
        prior = latest_by_type.get(test.test_type)
        if prior is None or test.tested_at > prior.tested_at:
            latest_by_type[test.test_type] = test

    automation_requested = any(
        mode in {"supervised", "automated"} for mode in payload.requested_execution_modes
    )
    required = AUTOMATION_REQUIRED_TEST_TYPES if automation_requested else REQUIRED_TEST_TYPES
    blockers: list[str] = []
    warnings: list[str] = []

    for test_type in sorted(required):
        test = latest_by_type.get(test_type)
        if test is None:
            blockers.append(f"MISSING_TEST:{test_type}")
        elif test.outcome == CommissioningTestOutcome.FAIL:
            blockers.append(f"FAILED_TEST:{test_type}")
        elif test.outcome == CommissioningTestOutcome.DEGRADED:
            warnings.append(f"DEGRADED_TEST:{test_type}")

    mandatory_interlocks = {
        "emergency_stop",
        "dry_run_protection",
        "overpressure_protection",
    }
    for name in sorted(mandatory_interlocks):
        if payload.safety_interlocks.get(name) is not True:
            blockers.append(f"INTERLOCK_NOT_VERIFIED:{name}")

    if automation_requested:
        for name in ("loss_of_communication_safe_state", "manual_override"):
            if payload.safety_interlocks.get(name) is not True:
                blockers.append(f"INTERLOCK_NOT_VERIFIED:{name}")
        if not payload.controller_id:
            blockers.append("CONTROLLER_ID_REQUIRED_FOR_AUTOMATION")

    if payload.valid_until <= current:
        blockers.append("CERTIFICATE_EXPIRED")

    permitted = ["recommendation_only"]
    if not any(reason.startswith("FAILED_TEST") for reason in blockers):
        permitted.extend(["manual_estimated", "manual_measured"])
    if not blockers:
        permitted.append("supervised")
        if "automated" in payload.requested_execution_modes:
            permitted.append("automated")

    if blockers:
        status = CommissioningState.FAIL
    elif warnings:
        status = CommissioningState.DEGRADED
    else:
        status = CommissioningState.PASS

    flow_curve_digest = None
    pressure_curve_digest = None
    power_curve_digest = None
    for test_type, attr in (
        ("pump_curve", "flow"),
        ("operating_pressure", "pressure"),
        ("voltage_drop", "power"),
    ):
        test = latest_by_type.get(test_type)
        if test:
            d = _digest(test.model_dump(mode="json"))
            if attr == "flow":
                flow_curve_digest = d
            elif attr == "pressure":
                pressure_curve_digest = d
            else:
                power_curve_digest = d

    body = {
        "certificate_id": payload.certificate_id,
        "tenant_id": payload.tenant_id,
        "field_id": payload.field_id,
        "season_id": payload.season_id,
        "system_id": payload.system_id,
        "machine_id": payload.machine_id,
        "pump_id": payload.pump_id,
        "controller_id": payload.controller_id,
        "commissioning_version": payload.commissioning_version,
        "status": status.value,
        "tested_at": payload.tested_at.isoformat(),
        "valid_until": payload.valid_until.isoformat(),
        "flow_curve_digest": flow_curve_digest,
        "pressure_curve_digest": pressure_curve_digest,
        "power_curve_digest": power_curve_digest,
        "specification_digest": payload.specification_digest,
        "capability_graph_digest": payload.capability_graph_digest,
        "safety_interlocks": dict(sorted(payload.safety_interlocks.items())),
        "execution_limits": payload.execution_limits,
        "permitted_execution_modes": sorted(set(permitted)),
        "blocking_failures": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "tests": [
            t.model_dump(mode="json") for t in sorted(payload.tests, key=lambda x: x.test_id)
        ],
        "issued_by": payload.issued_by,
        "reviewed_by": payload.reviewed_by,
        "supersedes_certificate_id": payload.supersedes_certificate_id,
    }
    return CommissioningCertificate(**body, certificate_digest=_digest(body))


def authorize_execution(
    *,
    requested_mode: str,
    certificate: CommissioningCertificate | None,
    now: datetime | None = None,
    decision_approved: bool,
    telemetry_fresh: bool,
    blocking_alarm: bool,
    execution_window_valid: bool,
    adapter_capable: bool,
) -> ExecutionAuthorization:
    current = now or datetime.now(UTC)
    reasons: list[str] = []
    automated = requested_mode in {"supervised", "automated"}

    if not decision_approved:
        reasons.append("DECISION_NOT_APPROVED")
    if not execution_window_valid:
        reasons.append("EXECUTION_WINDOW_INVALID")
    if blocking_alarm:
        reasons.append("BLOCKING_ALARM")

    if automated:
        if certificate is None:
            reasons.append("VALID_COMMISSIONING_CERTIFICATE_REQUIRED")
        else:
            if certificate.status not in {CommissioningState.PASS, CommissioningState.DEGRADED}:
                reasons.append("COMMISSIONING_CERTIFICATE_NOT_OPERATIONAL")
            if certificate.valid_until <= current:
                reasons.append("COMMISSIONING_CERTIFICATE_EXPIRED")
            if requested_mode not in certificate.permitted_execution_modes:
                reasons.append("EXECUTION_MODE_NOT_CERTIFIED")
        if not adapter_capable:
            reasons.append("ADAPTER_NOT_CAPABLE")
        if not telemetry_fresh:
            reasons.append("TELEMETRY_STALE")

    manual_allowed = (
        requested_mode
        in {
            "recommendation_only",
            "manual_estimated",
            "manual_measured",
        }
        and decision_approved
        and execution_window_valid
        and not blocking_alarm
    )
    execution_allowed = not reasons and (not automated or certificate is not None)
    body = {
        "execution_allowed": execution_allowed,
        "manual_execution_allowed": manual_allowed,
        "requested_mode": requested_mode,
        "certificate_id": certificate.certificate_id if certificate else None,
        "certificate_digest": certificate.certificate_digest if certificate else None,
        "blocking_reasons": sorted(set(reasons)),
    }
    return ExecutionAuthorization(**body, authorization_digest=_digest(body))
