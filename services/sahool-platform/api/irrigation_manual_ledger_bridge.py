"""IRR-X1.3 verified manual as-applied truth and water-ledger bridge.

The bridge keeps confirmation, independent verification, and ledger reconciliation
as separate durable actions. Only measured, verified manual irrigation can affect
canonical water truth. Reconciliation is idempotent by execution and digest.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ManualVerificationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_applied_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_id: str = Field(min_length=1)
    reviewed_at: datetime
    evidence_digests: list[str] = Field(min_length=1)
    volume_verified: bool
    timing_verified: bool
    field_verified: bool
    notes: str | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> ManualVerificationInput:
        for digest in self.evidence_digests:
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("INVALID_VERIFICATION_EVIDENCE_DIGEST")
        if self.reviewed_at > datetime.now(UTC):
            raise ValueError("VERIFICATION_TIME_IN_FUTURE")
        return self


class ManualVerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_id: str
    status: str
    ledger_eligible: bool
    blocking_reasons: list[str]
    verification_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified_at: datetime
    reviewer_id: str


class ManualLedgerEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str = "manual_irrigation_as_applied.v1"
    execution_id: str
    tenant_id: str
    field_id: str
    season_id: str
    applied_volume_m3: float = Field(gt=0)
    applied_depth_mm: float = Field(gt=0)
    observed_at: datetime
    as_applied_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    verification_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    ledger_event_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_manual_as_applied(
    *,
    execution_id: str,
    stored_as_applied: dict[str, Any],
    stored_as_applied_digest: str,
    execution_mode: str,
    confirmation: dict[str, Any],
    request: ManualVerificationInput,
) -> ManualVerificationResult:
    blockers: list[str] = []
    if request.as_applied_digest != stored_as_applied_digest:
        blockers.append("AS_APPLIED_DIGEST_MISMATCH")
    if execution_mode != "manual_measured":
        blockers.append("ONLY_MANUAL_MEASURED_CAN_BE_VERIFIED_FOR_LEDGER")
    if not bool(stored_as_applied.get("ledger_eligible")):
        blockers.append("CONFIRMED_AS_APPLIED_NOT_LEDGER_ELIGIBLE")
    if not str(stored_as_applied.get("quality", "")).startswith("measured"):
        blockers.append("MEASURED_WATER_EVIDENCE_REQUIRED")
    if not request.volume_verified:
        blockers.append("VOLUME_NOT_VERIFIED")
    if not request.timing_verified:
        blockers.append("TIMING_NOT_VERIFIED")
    if not request.field_verified:
        blockers.append("FIELD_IDENTITY_NOT_VERIFIED")

    confirmation_evidence = set(confirmation.get("evidence_digests") or [])
    supplied_evidence = set(request.evidence_digests)
    if confirmation_evidence and not confirmation_evidence.issubset(supplied_evidence):
        blockers.append("CONFIRMATION_EVIDENCE_NOT_COVERED")

    verified = not blockers
    payload = {
        "execution_id": execution_id,
        "as_applied_digest": stored_as_applied_digest,
        "reviewer_id": request.reviewer_id,
        "reviewed_at": request.reviewed_at.isoformat(),
        "evidence_digests": sorted(set(request.evidence_digests)),
        "volume_verified": request.volume_verified,
        "timing_verified": request.timing_verified,
        "field_verified": request.field_verified,
        "status": "verified" if verified else "rejected",
        "blocking_reasons": sorted(set(blockers)),
    }
    return ManualVerificationResult(
        execution_id=execution_id,
        status=payload["status"],
        ledger_eligible=verified,
        blocking_reasons=payload["blocking_reasons"],
        verification_digest=_digest(payload),
        verified_at=request.reviewed_at,
        reviewer_id=request.reviewer_id,
    )


def build_manual_water_ledger_event(
    *,
    execution: dict[str, Any],
    verification_digest: str,
) -> ManualLedgerEvent:
    if execution.get("state") != "verified":
        raise ValueError("MANUAL_EXECUTION_NOT_VERIFIED")
    if not execution.get("ledger_eligible"):
        raise ValueError("MANUAL_EXECUTION_NOT_LEDGER_ELIGIBLE")
    as_applied = execution.get("as_applied") or {}
    confirmation = execution.get("confirmation") or {}
    volume = float(as_applied.get("actual_volume_m3") or 0.0)
    depth = float(as_applied.get("actual_depth_mm") or 0.0)
    if volume <= 0 or depth <= 0:
        raise ValueError("INVALID_AS_APPLIED_WATER_QUANTITY")
    observed_at = confirmation.get("stopped_at") or execution.get("stopped_at")
    if isinstance(observed_at, str):
        observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if observed_at is None:
        raise ValueError("AS_APPLIED_OBSERVED_AT_REQUIRED")
    body = {
        "event_type": "manual_irrigation_as_applied.v1",
        "execution_id": str(execution["execution_id"]),
        "tenant_id": str(execution["tenant_id"]),
        "field_id": execution["field_id"],
        "season_id": execution["season_id"],
        "applied_volume_m3": round(volume, 3),
        "applied_depth_mm": round(depth, 4),
        "observed_at": observed_at.isoformat(),
        "as_applied_digest": execution["as_applied_digest"],
        "verification_digest": verification_digest,
    }
    return ManualLedgerEvent(**body, ledger_event_digest=_digest(body))
