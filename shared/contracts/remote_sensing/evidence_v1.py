from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from .base import ContractModel, require_aware_utc
from .enums import EvidenceRelationType, EvidenceVerificationState
from .identifiers import EvidenceRef, GeometryRef, Sha256Digest, TenantId


class EvidenceRefV1(ContractModel):
    evidence_ref: EvidenceRef
    tenant_id: TenantId
    source_system: str = Field(min_length=1, max_length=64)
    evidence_type: str = Field(min_length=1, max_length=64)
    relation_type: EvidenceRelationType
    captured_at: datetime
    content_hash: Sha256Digest
    verification_state: EvidenceVerificationState
    quality_grade: str | None = Field(default=None, pattern=r"^(A|B|C|D|F)$")
    valid_until: datetime | None = None
    geometry_ref: GeometryRef | None = None

    _timestamps = field_validator("captured_at", "valid_until")(
        lambda v: None if v is None else require_aware_utc(v)
    )


class EvidenceBundleV1(ContractModel):
    evidence: tuple[EvidenceRefV1, ...] = ()
