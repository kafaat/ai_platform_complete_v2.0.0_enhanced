"""Versioned request identity for durable, post-delivery imagery follow-up.

The timestamp is resolved from Decision SoR, never from the HTTP retry's clock.
An accepted delivery receipt is not evidence of physical execution or crop benefit.
"""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

POLICY_VERSION = "post-delivery-imagery/v1"


class ImageryFollowUpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)
    season_id: str = Field(min_length=1, max_length=100)
    execution_request_id: str = Field(min_length=1, max_length=100, pattern=r"^[\w-]+$")
    days_after: int = Field(default=5, ge=1, le=30)
    window_days: int = Field(default=7, ge=1, le=30)
    indicators: list[str] = Field(
        default_factory=lambda: ["ndvi", "ndmi"], min_length=1, max_length=2
    )

    @field_validator("indicators")
    @classmethod
    def normalize_indicators(cls, values: list[str]) -> list[str]:
        normalized = sorted({value.strip().lower() for value in values})
        if not normalized or not set(normalized) <= {"ndvi", "ndmi"}:
            raise ValueError("follow-up v1 supports ndvi and ndmi only")
        return normalized


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def request_identity(tenant: str, field: str, execution: str) -> str:
    parts = [str(UUID(tenant)), field, execution, POLICY_VERSION]
    return "rs10_" + hashlib.sha256(canonical_json(parts).encode()).hexdigest()


def request_digest(request: ImageryFollowUpRequest) -> str:
    return hashlib.sha256(canonical_json(request.model_dump()).encode()).hexdigest()
