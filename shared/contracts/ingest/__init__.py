"""عقود الإدخال الميدانيّ الخارجيّ (SCOUT-INGEST-01 / B1)."""

from shared.contracts.ingest.external_submission_v1 import (
    INGEST_CONTRACT_VERSION,
    SEVEN_CHECKS,
    ExternalSubmissionEnvelopeV1,
    IngestCheck,
    derive_dedup_key,
)

__all__ = [
    "INGEST_CONTRACT_VERSION",
    "SEVEN_CHECKS",
    "ExternalSubmissionEnvelopeV1",
    "IngestCheck",
    "derive_dedup_key",
]
