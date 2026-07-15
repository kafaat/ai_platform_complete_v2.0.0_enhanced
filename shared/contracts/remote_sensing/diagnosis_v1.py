from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from .base import ContractModel, require_aware_utc
from .enums import DiagnosisAssessmentStatus, VerificationRequirement
from .evidence_v1 import EvidenceBundleV1
from .identifiers import (
    AnomalyRef,
    DiagnosisRef,
    FieldId,
    ModelRef,
    SchemaVersion,
    SeasonId,
    TenantId,
    UserRef,
)


class DiagnosisHypothesisV1(ContractModel):
    schema_version: SchemaVersion = "1.0.0"
    diagnosis_ref: DiagnosisRef
    tenant_id: TenantId
    field_id: FieldId
    season_id: SeasonId
    primary_anomaly_ref: AnomalyRef
    related_anomaly_refs: tuple[AnomalyRef, ...] = ()
    suspected_condition: str = Field(min_length=1, max_length=128)
    alternative_conditions: tuple[str, ...] = ()
    alternative_assessment_note: str | None = Field(default=None, max_length=512)
    evidence_bundle: EvidenceBundleV1
    confidence: Decimal = Field(ge=0, le=1)
    confidence_method: str = Field(min_length=1, max_length=96)
    ground_verification_requirement: VerificationRequirement
    recommended_verification_methods: tuple[str, ...] = ()
    assessment_status: DiagnosisAssessmentStatus = DiagnosisAssessmentStatus.PENDING
    reviewed_by: UserRef | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = Field(default=None, max_length=2000)
    diagnosis_model_ref: ModelRef
    proposed_at: datetime
    updated_at: datetime | None = None

    _timestamps = field_validator("reviewed_at", "proposed_at", "updated_at")(
        lambda v: None if v is None else require_aware_utc(v)
    )

    @model_validator(mode="after")
    def validate_alternatives(self):
        if self.confidence < Decimal("0.90") and not (
            self.alternative_conditions or self.alternative_assessment_note
        ):
            raise ValueError("alternatives_or_assessment_note_required_below_high_confidence")
        return self
