"""Canonical SoilObservation.v1 contract."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

SOIL_OBSERVATION_CONTRACT_VERSION = "soil-observation.v1"


class SoilObservationSource(StrEnum):
    SENSOR = "sensor"
    LABORATORY = "laboratory"
    FIELD = "field"
    SMARTPHONE = "smartphone"
    SOILGRIDS = "soilgrids"
    REMOTE_SENSING = "remote_sensing"
    ANALOG_FIELDS = "analog_fields"
    MODEL = "model"


class SoilObservationQuality(StrEnum):
    ACCEPTED = "accepted"
    SUSPECT = "suspect"
    REJECTED = "rejected"
    UNCALIBRATED = "uncalibrated"


class SoilObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = SOIL_OBSERVATION_CONTRACT_VERSION
    observation_id: str = Field(default_factory=lambda: f"sob_{uuid4().hex}")
    tenant_id: str = Field(min_length=1)
    field_id: str = Field(min_length=1, max_length=128)
    zone_id: str | None = None
    property: str = Field(min_length=1, max_length=96)
    value: float | str | bool | None
    unit: str | None = None
    depth_from_cm: float = Field(default=0, ge=0)
    depth_to_cm: float = Field(default=30, gt=0)
    observed_at: datetime
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_type: SoilObservationSource
    source_id: str | None = None
    procedure_id: str | None = None
    calibration_id: str | None = None
    quality_status: SoilObservationQuality = SoilObservationQuality.ACCEPTED
    quality_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)
    idempotency_key: str = Field(min_length=1, max_length=256)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _integrity(self) -> SoilObservation:
        if self.contract_version != SOIL_OBSERVATION_CONTRACT_VERSION:
            raise ValueError("soil_observation_contract_version_unsupported")
        if self.depth_to_cm <= self.depth_from_cm:
            raise ValueError("soil_observation_depth_invalid")
        if self.received_at < self.observed_at:
            raise ValueError("soil_observation_received_before_observed")
        return self
