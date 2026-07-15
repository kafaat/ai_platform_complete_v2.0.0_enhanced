from typing import Literal

from pydantic import Field

from ..base import ContractModel
from ..identifiers import FieldId, ProcessingRunRef, SceneId, SeasonId
from ..raster_asset_v1 import RasterAssetPersistedV1
from .envelope_v1 import EventEnvelopeV1


class RasterAssetPersistedPayloadV1(ContractModel):
    asset: RasterAssetPersistedV1


class RasterAssetPersistedEventV1(EventEnvelopeV1[RasterAssetPersistedPayloadV1]):
    event_type: Literal["sahool.rs.asset.persisted.v1"] = "sahool.rs.asset.persisted.v1"
    aggregate_type: Literal["raster_asset"] = "raster_asset"


class RasterAssetFailedPayloadV1(ContractModel):
    run_ref: ProcessingRunRef
    field_id: FieldId
    season_id: SeasonId | None = None
    scene_id: SceneId
    failed_stage: str = Field(min_length=1, max_length=96)
    error_code: str = Field(min_length=1, max_length=96)
    error_detail: str = Field(min_length=1, max_length=2000)
    retry_eligible: bool
    retry_count: int = Field(ge=0)


class RasterAssetFailedEventV1(EventEnvelopeV1[RasterAssetFailedPayloadV1]):
    event_type: Literal["sahool.rs.asset.failed.v1"] = "sahool.rs.asset.failed.v1"
    aggregate_type: Literal["raster_processing_run"] = "raster_processing_run"
