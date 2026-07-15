"""Strict request contracts for RS-6/RS-7 anomaly routes.

Kept outside ``routers`` so tests, workers, and schema tools can import the
contracts without triggering FastAPI router registration or a circular import
through ``main``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DetectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    season_id: str = Field(min_length=1, max_length=128)
    indicator: str = Field(default="ndvi", min_length=1, max_length=64)
    current_stage: str | None = Field(default=None, max_length=128)
    stage_by_observation: dict[str, str] = Field(default_factory=dict)
    max_history: int = Field(default=12, ge=1, le=60)
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
    reason_codes: list[str] = Field(default_factory=list)
    completed_at: datetime

    @field_validator("completed_at")
    @classmethod
    def completed_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("completed_at must be timezone-aware")
        return value
