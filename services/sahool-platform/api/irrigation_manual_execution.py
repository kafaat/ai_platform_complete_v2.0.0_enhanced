"""IRR-X1.2 governed manual irrigation execution lifecycle.

Keeps recommendation, approval, execution, confirmation, as-applied truth and
ledger reconciliation as distinct legal states. No vendor adapter is required.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ManualExecutionState(StrEnum):
    RECOMMENDED = "recommended"
    APPROVED = "approved"
    STARTED = "started"
    STOPPED = "stopped"
    CONFIRMED = "confirmed"
    VERIFIED = "verified"
    RECONCILED = "reconciled"
    CANCELLED = "cancelled"


class ManualExecutionMode(StrEnum):
    RECOMMENDATION_ONLY = "recommendation_only"
    MANUAL_ESTIMATED = "manual_estimated"
    MANUAL_MEASURED = "manual_measured"


ALLOWED_TRANSITIONS: dict[ManualExecutionState, set[ManualExecutionState]] = {
    ManualExecutionState.RECOMMENDED: {
        ManualExecutionState.APPROVED,
        ManualExecutionState.CANCELLED,
    },
    ManualExecutionState.APPROVED: {ManualExecutionState.STARTED, ManualExecutionState.CANCELLED},
    ManualExecutionState.STARTED: {ManualExecutionState.STOPPED},
    ManualExecutionState.STOPPED: {ManualExecutionState.CONFIRMED, ManualExecutionState.CANCELLED},
    ManualExecutionState.CONFIRMED: {ManualExecutionState.VERIFIED},
    ManualExecutionState.VERIFIED: {ManualExecutionState.RECONCILED},
    ManualExecutionState.RECONCILED: set(),
    ManualExecutionState.CANCELLED: set(),
}


class ManualRecommendationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_id: str
    tenant_id: str
    field_id: str
    season_id: str
    system_id: str
    recommendation_id: str
    recommendation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: ManualExecutionMode
    target_depth_mm: float = Field(gt=0)
    target_volume_m3: float = Field(gt=0)
    nominal_flow_m3_h: float | None = Field(default=None, gt=0)
    valid_from: datetime
    valid_until: datetime
    created_by: str

    @model_validator(mode="after")
    def validate_mode(self) -> ManualRecommendationInput:
        if self.valid_until <= self.valid_from:
            raise ValueError("EXECUTION_WINDOW_INVALID")
        if self.mode == ManualExecutionMode.MANUAL_ESTIMATED and self.nominal_flow_m3_h is None:
            raise ValueError("NOMINAL_FLOW_REQUIRED_FOR_ESTIMATED_MODE")
        return self


class ManualExecutionConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    started_at: datetime
    stopped_at: datetime
    completion_ratio: float = Field(gt=0, le=1)
    meter_start_m3: float | None = Field(default=None, ge=0)
    meter_end_m3: float | None = Field(default=None, ge=0)
    measured_flow_m3_h: float | None = Field(default=None, gt=0)
    estimated_flow_m3_h: float | None = Field(default=None, gt=0)
    interruptions_minutes: float = Field(default=0, ge=0)
    pressure_bar: float | None = Field(default=None, ge=0)
    evidence_digests: list[str] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_confirmation(self) -> ManualExecutionConfirmation:
        if self.stopped_at <= self.started_at:
            raise ValueError("EXECUTION_TIME_WINDOW_INVALID")
        if self.meter_start_m3 is not None and self.meter_end_m3 is not None:
            if self.meter_end_m3 < self.meter_start_m3:
                raise ValueError("METER_READING_REGRESSION")
        for digest in self.evidence_digests:
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("INVALID_EVIDENCE_DIGEST")
        return self


class ManualAsAppliedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_id: str
    mode: ManualExecutionMode
    quality: str
    actual_runtime_h: float
    actual_volume_m3: float
    actual_depth_mm: float
    completion_ratio: float
    ledger_eligible: bool
    blocking_reasons: list[str]
    as_applied_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def transition_manual_execution(
    current: ManualExecutionState, target: ManualExecutionState
) -> ManualExecutionState:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"INVALID_MANUAL_EXECUTION_TRANSITION:{current.value}->{target.value}")
    return target


def derive_manual_as_applied(
    recommendation: ManualRecommendationInput,
    confirmation: ManualExecutionConfirmation,
) -> ManualAsAppliedResult:
    runtime_h = (confirmation.stopped_at - confirmation.started_at).total_seconds() / 3600.0
    runtime_h = max(0.0, runtime_h - confirmation.interruptions_minutes / 60.0)
    blockers: list[str] = []
    quality = "estimated"
    volume: float | None = None

    if confirmation.meter_start_m3 is not None and confirmation.meter_end_m3 is not None:
        volume = confirmation.meter_end_m3 - confirmation.meter_start_m3
        quality = "measured_meter"
    elif confirmation.measured_flow_m3_h is not None:
        volume = confirmation.measured_flow_m3_h * runtime_h
        quality = "measured_flow"
    elif confirmation.estimated_flow_m3_h is not None:
        volume = confirmation.estimated_flow_m3_h * runtime_h
        quality = "estimated"
    elif recommendation.nominal_flow_m3_h is not None:
        volume = recommendation.nominal_flow_m3_h * runtime_h
        quality = "estimated_nominal"
    else:
        blockers.append("NO_VOLUME_EVIDENCE")
        volume = 0.0

    volume *= confirmation.completion_ratio
    area_ha = recommendation.target_volume_m3 / (recommendation.target_depth_mm * 10.0)
    depth = volume / (area_ha * 10.0) if area_ha > 0 else 0.0
    measured = quality.startswith("measured")
    ledger_eligible = measured and not blockers and volume > 0
    if recommendation.mode == ManualExecutionMode.MANUAL_MEASURED and not measured:
        blockers.append("MEASURED_MODE_REQUIRES_MEASURED_EVIDENCE")
        ledger_eligible = False

    body = {
        "execution_id": recommendation.execution_id,
        "mode": recommendation.mode.value,
        "quality": quality,
        "actual_runtime_h": round(runtime_h, 4),
        "actual_volume_m3": round(volume, 3),
        "actual_depth_mm": round(depth, 4),
        "completion_ratio": confirmation.completion_ratio,
        "ledger_eligible": ledger_eligible,
        "blocking_reasons": sorted(set(blockers)),
    }
    return ManualAsAppliedResult(**body, as_applied_digest=_digest(body))
