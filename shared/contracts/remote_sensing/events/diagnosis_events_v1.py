from typing import Literal

from ..base import ContractModel
from ..diagnosis_v1 import DiagnosisHypothesisV1
from .envelope_v1 import EventEnvelopeV1


class DiagnosisProposedPayloadV1(ContractModel):
    diagnosis: DiagnosisHypothesisV1


class DiagnosisProposedEventV1(EventEnvelopeV1[DiagnosisProposedPayloadV1]):
    event_type: Literal["sahool.rs.diagnosis.proposed.v1"] = "sahool.rs.diagnosis.proposed.v1"
    aggregate_type: Literal["diagnosis_hypothesis"] = "diagnosis_hypothesis"
