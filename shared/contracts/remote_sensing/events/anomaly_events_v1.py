from datetime import datetime
from typing import Literal

from pydantic import field_validator

from ..anomaly_v1 import SignalAnomalyV1
from ..base import ContractModel, require_aware_utc
from ..identifiers import AnomalyRef, EvidenceRef
from .envelope_v1 import EventEnvelopeV1


class AnomalyDetectedPayloadV1(ContractModel):
    anomaly: SignalAnomalyV1


class AnomalyDetectedEventV1(EventEnvelopeV1[AnomalyDetectedPayloadV1]):
    event_type: Literal["sahool.rs.anomaly.detected.v1"] = "sahool.rs.anomaly.detected.v1"
    aggregate_type: Literal["signal_anomaly"] = "signal_anomaly"


class AnomalyDispositionPayloadV1(ContractModel):
    anomaly_ref: AnomalyRef
    disposition: Literal["confirmed", "rejected", "inconclusive"]
    verification_evidence_refs: tuple[EvidenceRef, ...] = ()
    disposition_reason_codes: tuple[str, ...] = ()
    decided_at: datetime
    _timestamp = field_validator("decided_at")(require_aware_utc)


class AnomalyDispositionEventV1(EventEnvelopeV1[AnomalyDispositionPayloadV1]):
    event_type: Literal["sahool.rs.anomaly.dispositioned.v1"] = "sahool.rs.anomaly.dispositioned.v1"
    aggregate_type: Literal["signal_anomaly"] = "signal_anomaly"
