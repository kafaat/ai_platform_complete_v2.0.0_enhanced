"""Strict request contracts for RS-6/RS-7 anomaly routes.

Kept outside ``routers`` so tests, workers, and schema tools can import the
contracts without triggering FastAPI router registration or a circular import
through ``main``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shared.contracts.remote_sensing import EvidenceRefV1


class DetectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    season_id: str = Field(min_length=1, max_length=128)
    indicator: str = Field(default="ndvi", min_length=1, max_length=64)
    current_stage: str | None = Field(default=None, max_length=128)
    stage_by_observation: dict[str, str] = Field(default_factory=dict)
    max_history: int = Field(default=12, ge=1, le=60)
    max_gap_days: int = Field(default=32, ge=1, le=90)
    min_deviation_percent: Decimal = Field(default=Decimal("7"), ge=0, le=100)
    auto_request_verification: bool = False


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    target_status: Literal["triaged", "resolved"]
    reason_codes: list[str] = Field(default_factory=list)


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    priority: str | None = Field(default=None, max_length=32)


class VerificationCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    task_ref: str = Field(min_length=1, max_length=256)
    verification_result: Literal["confirmed", "rejected", "inconclusive"]
    evidence_refs: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRefV1] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    completed_at: datetime

    @field_validator("evidence", mode="before")
    @classmethod
    def parse_evidence_wire_contract(cls, values):
        if not isinstance(values, list):
            raise ValueError("evidence_must_be_an_array")
        return [
            EvidenceRefV1.model_validate_json(json.dumps(e)) if isinstance(e, dict) else e
            for e in values
        ]

    @field_validator("completed_at")
    @classmethod
    def completed_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("completed_at must be timezone-aware")
        if value > datetime.now(UTC):
            raise ValueError("completed_at cannot be in the future")
        return value

    @model_validator(mode="after")
    def confirmed_requires_original_evidence(self):
        if self.verification_result != "confirmed":
            return self
        refs = [e.evidence_ref for e in self.evidence]
        if not refs or len(set(refs)) != len(refs) or set(refs) != set(self.evidence_refs):
            raise ValueError("confirmed_verification_requires_matching_evidence_metadata")
        if any(
            e.verification_state != "verified" or e.captured_at > self.completed_at
            for e in self.evidence
        ):
            raise ValueError("invalid_verification_evidence_state_or_time")
        return self
