"""P4 governed soil decision, execution, verification and learning contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class ApprovalRequirement(StrEnum):
    none = "none"
    agronomist = "agronomist"
    soil_specialist = "soil_specialist"
    engineer = "engineer"
    dual = "dual"


class SoilActionPolicy(BaseModel):
    action_type: str
    minimum_evidence_level: str = "baseline_only"
    required_properties: list[str] = Field(default_factory=list)
    max_evidence_age_days: int | None = None
    required_depth_cm: int | None = None
    requires_water_profile: bool = False
    requires_drainage_verification: bool = False
    approval_requirement: ApprovalRequirement = ApprovalRequirement.none
    block_on_conflict: bool = True


class SoilActionEvaluation(BaseModel):
    allowed: bool
    code: str
    reasons: list[str] = Field(default_factory=list)
    missing_properties: list[str] = Field(default_factory=list)
    stale_properties: list[str] = Field(default_factory=list)
    approval_requirement: ApprovalRequirement = ApprovalRequirement.none


class SoilExecutionRecord(BaseModel):
    execution_id: str = Field(default_factory=lambda: f"sex_{uuid4().hex}")
    tenant_id: str
    field_id: str
    decision_id: str
    action_type: str
    profile_hash: str
    approved_by: list[str] = Field(default_factory=list)
    planned: dict[str, Any] = Field(default_factory=dict)
    actual: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SoilVerificationRecord(BaseModel):
    verification_id: str = Field(default_factory=lambda: f"svr_{uuid4().hex}")
    tenant_id: str
    field_id: str
    execution_id: str
    before: dict[str, float | None] = Field(default_factory=dict)
    after: dict[str, float | None] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    verifier_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_measurement(self):
        if not self.before and not self.after:
            raise ValueError("before or after measurements required")
        return self


class SoilOutcomeRecord(BaseModel):
    outcome_id: str = Field(default_factory=lambda: f"sout_{uuid4().hex}")
    tenant_id: str
    field_id: str
    execution_id: str
    verification_id: str | None = None
    metrics: dict[str, float | None] = Field(default_factory=dict)
    effectiveness_score: float = Field(ge=0, le=1)
    salinity_rebound: bool | None = None
    crop_establishment_score: float | None = Field(default=None, ge=0, le=1)
    yield_uniformity_score: float | None = Field(default=None, ge=0, le=1)
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SoilLearningAttribution(BaseModel):
    learning_id: str = Field(default_factory=lambda: f"slrn_{uuid4().hex}")
    tenant_id: str
    field_id: str
    outcome_id: str
    execution_id: str
    source_profile_hash: str
    action_type: str
    feature_snapshot: dict[str, Any] = Field(default_factory=dict)
    target_metrics: dict[str, float | None] = Field(default_factory=dict)
    eligible_for_training: bool = False
    exclusion_reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
