from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from .base import ContractModel, require_aware_utc
from .evidence_v1 import EvidenceBundleV1
from .identifiers import (
    DecisionReferralRef,
    DiagnosisRef,
    FieldId,
    FieldStateRef,
    SchemaVersion,
    SeasonId,
    SoilContextRef,
    TenantId,
    WeatherContextRef,
)


class FieldContextRefV1(ContractModel):
    field_state_ref: FieldStateRef
    soil_context_ref: SoilContextRef | None = None
    weather_context_ref: WeatherContextRef | None = None


class SuggestedActionClassV1(ContractModel):
    action_type: str = Field(min_length=1, max_length=64)
    urgency: str = Field(pattern=r"^(immediate|high|medium|low|routine)$")
    expected_benefit: str | None = Field(default=None, max_length=512)
    risk_if_ignored: str | None = Field(default=None, max_length=512)


class ValidityContextV1(ContractModel):
    valid_from: datetime
    valid_until: datetime
    weather_window_required: bool = False
    crop_stage_constraint: str | None = Field(default=None, max_length=96)
    _timestamps = field_validator("valid_from", "valid_until")(require_aware_utc)

    @model_validator(mode="after")
    def validate_window(self):
        if self.valid_from >= self.valid_until:
            raise ValueError("invalid_validity_window")
        return self


class DiagnosisDecisionReferralV1(ContractModel):
    schema_version: SchemaVersion = "1.0.0"
    referral_ref: DecisionReferralRef
    tenant_id: TenantId
    field_id: FieldId
    season_id: SeasonId
    diagnosis_ref: DiagnosisRef
    field_context: FieldContextRefV1
    evidence_bundle: EvidenceBundleV1
    suggested_action_class: SuggestedActionClassV1 | None = None
    validity_context: ValidityContextV1 | None = None
    referred_at: datetime
    _timestamp = field_validator("referred_at")(require_aware_utc)
