from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .base import ContractModel, require_aware_utc
from .enums import PublicationStatus, ValueType
from .identifiers import (
    AssetRef,
    FieldId,
    GeometryRef,
    ObservationRef,
    ProcessingRunRef,
    SchemaVersion,
    SeasonId,
    SemVer,
    Sha256Digest,
    TenantId,
)
from .quality_v1 import ObservationQualityV1


class IndicatorDefinitionRefV1(ContractModel):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    semantic_version: SchemaVersion
    value_type: ValueType
    unit: str | None = Field(default=None, max_length=32)
    algorithm_ref: str | None = Field(default=None, max_length=256)


class ContinuousSummaryV1(ContractModel):
    kind: Literal["continuous"] = "continuous"
    mean: Decimal
    median: Decimal | None = None
    p10: Decimal | None = None
    p90: Decimal | None = None
    stddev: Decimal | None = Field(default=None, ge=0)
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    sample_count: int | None = Field(default=None, ge=0)


class CategoricalSummaryV1(ContractModel):
    kind: Literal["categorical"] = "categorical"
    class_distribution: dict[str, Decimal]
    dominant_class: str | None = None

    @model_validator(mode="after")
    def validate_distribution(self):
        if any(v < 0 or v > 1 for v in self.class_distribution.values()):
            raise ValueError("class_distribution_out_of_range")
        return self


class SpatialSummaryV1(ContractModel):
    kind: Literal["spatial"] = "spatial"
    geometry_ref: GeometryRef
    feature_count: int = Field(ge=0)


ObservationSummaryV1 = Annotated[
    ContinuousSummaryV1 | CategoricalSummaryV1 | SpatialSummaryV1, Field(discriminator="kind")
]


class ObservationUncertaintyV1(ContractModel):
    method: str = Field(min_length=1, max_length=96)
    confidence: Decimal = Field(ge=0, le=1)
    detail: str | None = Field(default=None, max_length=512)


class ObservationLineageV1(ContractModel):
    asset_ref: AssetRef
    processing_run_ref: ProcessingRunRef
    input_hash: Sha256Digest
    output_hash: Sha256Digest
    pipeline_version: SemVer


class CanonicalObservationV1(ContractModel):
    schema_version: SchemaVersion = "1.0.0"
    observation_ref: ObservationRef
    tenant_id: TenantId
    field_id: FieldId
    season_id: SeasonId
    asset_ref: AssetRef
    indicator: IndicatorDefinitionRefV1
    acquired_at: datetime
    observed_at: datetime
    published_at: datetime
    summary: ObservationSummaryV1
    observation_quality: ObservationQualityV1
    uncertainty: ObservationUncertaintyV1
    lineage: ObservationLineageV1
    publication_status: PublicationStatus
    supersedes: ObservationRef | None = None

    _timestamps = field_validator("acquired_at", "observed_at", "published_at")(require_aware_utc)

    @model_validator(mode="after")
    def validate_integrity(self):
        if self.acquired_at > self.observed_at:
            raise ValueError("acquired_at_after_observed_at")
        if self.observed_at > self.published_at:
            raise ValueError("observed_at_after_published_at")
        expected = {
            ValueType.CONTINUOUS: "continuous",
            ValueType.MODEL_ESTIMATE: "continuous",
            ValueType.CATEGORICAL: "categorical",
            ValueType.SPATIAL: "spatial",
        }[self.indicator.value_type]
        if self.summary.kind != expected:
            raise ValueError("summary_kind_does_not_match_value_type")
        if self.supersedes == self.observation_ref:
            raise ValueError("observation_cannot_supersede_itself")
        return self
