"""P6 runtime and production certification contracts for the soil domain."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

CheckStatus = Literal["pending", "passed", "failed", "skipped"]
RunStatus = Literal["draft", "running", "blocked", "ready_for_approval", "certified", "revoked"]


class CertificationEvidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"sce_{uuid4().hex}")
    check_name: str
    evidence_type: str
    uri: str | None = None
    sha256: str
    summary: dict[str, Any] = Field(default_factory=dict)
    produced_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CertificationCheck(BaseModel):
    check_name: str
    status: CheckStatus = "pending"
    required: bool = True
    evidence_ids: list[str] = Field(default_factory=list)
    observed_value: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    reasons: list[str] = Field(default_factory=list)
    duration_ms: float | None = Field(default=None, ge=0)


class RuntimeCertificationRun(BaseModel):
    run_id: str = Field(default_factory=lambda: f"scr_{uuid4().hex}")
    tenant_id: str
    release_ref: str
    environment: str
    status: RunStatus = "draft"
    migrations_applied_through: str | None = None
    checks: list[CertificationCheck] = Field(default_factory=list)
    evidence: list[CertificationEvidence] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    approvals: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    manifest_sha256: str | None = None

    @model_validator(mode="after")
    def unique_check_names(self):
        names = [c.check_name for c in self.checks]
        if len(names) != len(set(names)):
            raise ValueError("duplicate certification check names")
        return self


class CertificationPolicy(BaseModel):
    required_checks: list[str] = Field(
        default_factory=lambda: [
            "migrations",
            "rls",
            "concurrency",
            "lease_recovery",
            "retry_dead_letter",
            "e2e",
            "lineage",
            "performance",
            "calibration",
            "rollback",
        ]
    )
    min_approvals: int = Field(default=2, ge=2)
    max_p95_ms: float = Field(default=1500, gt=0)
    max_error_rate: float = Field(default=0.01, ge=0, le=1)
    max_queue_lag_seconds: int = Field(default=300, ge=0)
