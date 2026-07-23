"""P5 field validation, regional calibration and certification contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class ValidationMeasurement(BaseModel):
    property_name: str
    measured_value: float
    predicted_value: float | None = None
    unit: str
    depth_cm: int | None = Field(default=None, ge=0, le=500)
    method: str
    observed_at: datetime
    evidence_id: str


class FieldValidationRecord(BaseModel):
    validation_id: str = Field(default_factory=lambda: f"sfv_{uuid4().hex}")
    tenant_id: str
    field_id: str
    governorate: str
    crop: str | None = None
    campaign_id: str
    season_id: str | None = None
    measurements: list[ValidationMeasurement]
    gps_accuracy_m: float | None = Field(default=None, ge=0)
    reviewer_id: str | None = None
    accepted: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def require_measurements(self):
        if not self.measurements:
            raise ValueError("measurements required")
        return self


class CalibrationMetric(BaseModel):
    property_name: str
    n: int = Field(ge=0)
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None
    r2: float | None = None
    spatial_cv: bool = True


class RegionalCalibrationArtifact(BaseModel):
    calibration_id: str = Field(default_factory=lambda: f"src_{uuid4().hex}")
    tenant_id: str
    governorate: str
    crop: str | None = None
    product_type: str
    dataset_version: str
    source_validation_ids: list[str]
    metrics: list[CalibrationMetric]
    minimum_samples: int = Field(default=20, ge=3)
    status: str = "candidate"
    model_version: str
    training_data_hash: str
    leakage_checks_passed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AcceptanceThreshold(BaseModel):
    product_type: str
    property_name: str
    min_samples: int = 20
    max_mae: float | None = None
    max_rmse: float | None = None
    max_abs_bias: float | None = None
    min_r2: float | None = None
    require_spatial_cv: bool = True


class CalibrationPromotionDecision(BaseModel):
    calibration_id: str
    promotable: bool
    reasons: list[str] = Field(default_factory=list)
    evaluated_metrics: list[dict[str, Any]] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=lambda: ["soil_scientist", "ml_reviewer"])


class ProductionCertificationRecord(BaseModel):
    certification_id: str = Field(default_factory=lambda: f"spc_{uuid4().hex}")
    tenant_id: str
    release_ref: str
    environment: str
    migrations_applied_through: str
    rls_passed: bool = False
    concurrency_passed: bool = False
    e2e_passed: bool = False
    lineage_passed: bool = False
    performance_passed: bool = False
    calibration_passed: bool = False
    evidence_uris: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    certified: bool = False
    certified_by: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LearningDatasetManifest(BaseModel):
    dataset_id: str = Field(default_factory=lambda: f"sld_{uuid4().hex}")
    tenant_id: str
    name: str
    version: str
    source_learning_ids: list[str]
    feature_schema_version: str
    target_schema_version: str
    train_count: int = 0
    validation_count: int = 0
    test_count: int = 0
    split_strategy: str = "spatial_temporal_grouped"
    leakage_checks_passed: bool = False
    lineage_complete: bool = False
    dataset_hash: str
    eligible_for_training: bool = False
    exclusion_reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
