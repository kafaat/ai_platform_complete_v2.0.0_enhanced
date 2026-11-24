"""Explicit human assessment of a signal; never a diagnosis or an execution receipt.

This bridge is opt-in. A pin review approves its own image/notes, while the
separate assessment below states what that visit establishes about the signal.
Only a reviewer can record it, against an owner-resolved context and revision.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def wire(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): wire(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [wire(v) for v in value]
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("aware_time_required")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    return value


def canonical(value: Any) -> str:
    return json.dumps(
        wire(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class LinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: UUID
    inspection_task_id: UUID
    season_binding: Literal["canonical_season", "accepted_record"]
    expected_revision: int = Field(ge=0, le=2147483646, strict=True)
    expected_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason", mode="before")
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value


class AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: UUID
    link_revision: int = Field(ge=1, le=2147483647, strict=True)
    expected_inspection_revision: int = Field(ge=1, le=2147483647, strict=True)
    evidence_version: int = Field(ge=1, le=2147483647, strict=True)
    verification_result: Literal["confirmed", "rejected", "inconclusive"]
    # This is a manually reviewed field check, not an agronomically calibrated
    # classifier. Site-only observations cannot confirm/refute the whole target.
    protocol: Literal["manual-signal-field-check/v1"]
    coverage: Literal["inspection_site_only", "anomaly_target_reviewed"]
    observations: str = Field(min_length=1, max_length=4000)
    coverage_basis: str = Field(min_length=1, max_length=4000)
    limitations: str = Field(min_length=1, max_length=4000)
    reason_codes: list[str] = Field(min_length=1, max_length=32)

    @field_validator("observations", "coverage_basis", "limitations", mode="before")
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("reason_codes")
    @classmethod
    def _codes(cls, value):
        if any(not c.strip() or len(c) > 128 for c in value) or len(value) != len(set(value)):
            raise ValueError("distinct_nonempty_reason_codes_required")
        return value

    @model_validator(mode="after")
    def _coverage(self):
        if self.coverage == "inspection_site_only" and self.verification_result != "inconclusive":
            raise ValueError("site_only_evidence_cannot_decide_the_anomaly_target")
        return self


def assessment_record(
    request: AssessmentRequest,
    *,
    scope: dict,
    inspection: dict,
    reviewer: str,
    reviewer_role: str,
    completed_at: datetime,
) -> dict:
    return wire(
        {
            "schema": "sahool.scouting-verification-assessment/v1",
            "request": request.model_dump(mode="json"),
            "scope": scope,
            "inspection": inspection,
            "reviewer": reviewer,
            "reviewer_role": reviewer_role,
            "completed_at": completed_at,
            "meaning": "human_review_of_observed_signal_only",
            "causal_diagnosis": None,
            "execution_verified": False,
            "training_label_approved": False,
        }
    )
