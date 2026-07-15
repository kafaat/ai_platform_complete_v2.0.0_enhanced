from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import Field, field_validator

from ..base import ContractModel, require_aware_utc
from ..identifiers import (
    CorrelationId,
    EventId,
    IdempotencyKey,
    SchemaVersion,
    SemVer,
    ServiceName,
    TenantId,
    TraceParent,
)

PayloadT = TypeVar("PayloadT", bound=ContractModel)


class EventEnvelopeV1(ContractModel, Generic[PayloadT]):
    event_id: EventId
    event_type: str = Field(min_length=1, max_length=160)
    schema_version: SchemaVersion = "1.0.0"
    occurred_at: datetime
    producer: ServiceName
    producer_version: SemVer
    tenant_id: TenantId
    correlation_id: CorrelationId
    causation_id: EventId | None = None
    aggregate_type: str = Field(min_length=1, max_length=64)
    aggregate_id: str = Field(min_length=1, max_length=256)
    aggregate_version: int = Field(ge=1)
    idempotency_key: IdempotencyKey
    traceparent: TraceParent | None = None
    payload: PayloadT
    _timestamp = field_validator("occurred_at")(require_aware_utc)
