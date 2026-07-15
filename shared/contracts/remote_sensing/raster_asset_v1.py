from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from .base import ContractModel, require_aware_utc
from .identifiers import (
    AssetRef,
    FieldId,
    ProcessingRunRef,
    RasterArtifactRef,
    SceneId,
    SchemaVersion,
    SeasonId,
    SemVer,
    ServiceName,
    TenantId,
)
from .quality_v1 import RasterAssetQualityV1


class RasterAssetPersistedV1(ContractModel):
    schema_version: SchemaVersion = "1.0.0"
    asset_ref: AssetRef
    tenant_id: TenantId
    field_id: FieldId
    season_id: SeasonId | None = None
    provider: str = Field(min_length=1, max_length=64)
    platform: str = Field(min_length=1, max_length=64)
    sensor: str = Field(min_length=1, max_length=64)
    scene_id: SceneId
    product_type: str = Field(min_length=1, max_length=64)
    acquired_at: datetime
    processed_at: datetime
    persisted_at: datetime
    cog_artifact_ref: RasterArtifactRef
    asset_quality: RasterAssetQualityV1
    processing_run_ref: ProcessingRunRef
    producer: ServiceName = "raster-service"
    producer_version: SemVer
    processing_level: str | None = Field(default=None, max_length=64)

    _timestamps = field_validator("acquired_at", "processed_at", "persisted_at")(require_aware_utc)

    @model_validator(mode="after")
    def validate_timeline(self):
        if self.acquired_at > self.processed_at:
            raise ValueError("acquired_at_after_processed_at")
        if self.processed_at > self.persisted_at:
            raise ValueError("processed_at_after_persisted_at")
        return self
