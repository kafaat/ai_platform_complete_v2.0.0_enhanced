from typing import Literal

from ..base import ContractModel
from ..identifiers import AssetRef, FieldId, ObservationRef, SeasonId
from ..observation_v1 import CanonicalObservationV1
from ..quality_v1 import ObservationQualityV1
from .envelope_v1 import EventEnvelopeV1


class ObservationPublishedPayloadV1(ContractModel):
    observation: CanonicalObservationV1


class ObservationPublishedEventV1(EventEnvelopeV1[ObservationPublishedPayloadV1]):
    event_type: Literal["sahool.rs.observation.published.v1"] = "sahool.rs.observation.published.v1"
    aggregate_type: Literal["field_observation"] = "field_observation"


class ObservationRejectedPayloadV1(ContractModel):
    observation_ref: ObservationRef
    asset_ref: AssetRef
    field_id: FieldId
    season_id: SeasonId
    indicator_code: str
    quality: ObservationQualityV1
    retry_eligible: bool


class ObservationRejectedEventV1(EventEnvelopeV1[ObservationRejectedPayloadV1]):
    event_type: Literal["sahool.rs.observation.rejected.v1"] = "sahool.rs.observation.rejected.v1"
    aggregate_type: Literal["field_observation"] = "field_observation"
