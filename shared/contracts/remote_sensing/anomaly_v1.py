from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_validator

from .base import ContractModel, require_aware_utc
from .enums import AnomalyStatus, Severity, VerificationRequirement
from .evidence_v1 import EvidenceBundleV1
from .identifiers import (
    AnomalyRef,
    FieldId,
    GeometryRef,
    ModelRef,
    ObservationRef,
    ProcessingRunRef,
    SchemaVersion,
    SeasonId,
    TenantId,
)


class BaselineRefV1(ContractModel):
    baseline_type: str = Field(min_length=1, max_length=64)
    baseline_run_ref: ProcessingRunRef
    observation_refs: tuple[ObservationRef, ...] = ()
    expected_value: Decimal | None = None
    expected_confidence: Decimal | None = Field(default=None, ge=0, le=1)


class SignalAnomalyV1(ContractModel):
    schema_version: SchemaVersion = "1.0.0"
    anomaly_ref: AnomalyRef
    tenant_id: TenantId
    field_id: FieldId
    season_id: SeasonId
    detection_run_ref: ProcessingRunRef
    primary_observation_ref: ObservationRef
    signal_type: str = Field(min_length=1, max_length=96)
    geometry_ref: GeometryRef | None = None
    affected_area_ha: Decimal | None = Field(default=None, ge=0)
    deviation: Decimal
    deviation_percent: Decimal | None = None
    baseline_refs: tuple[BaselineRefV1, ...] = Field(min_length=1)
    severity: Severity
    confidence: Decimal = Field(ge=0, le=1)
    evidence_bundle: EvidenceBundleV1
    verification_requirement: VerificationRequirement
    verification_deadline: datetime | None = None
    status: AnomalyStatus
    detector_model_ref: ModelRef
    detected_at: datetime
    updated_at: datetime | None = None

    _timestamps = field_validator("verification_deadline", "detected_at", "updated_at")(
        lambda v: None if v is None else require_aware_utc(v)
    )
