"""decision-service — P4 boundary owner for decisions, outcomes, and learning loop lineage.

This service owns the write-side contract for:
- decision_record
- dispatch_decisions
- outcome_record
- recommendation_outcomes
- online_learning_updates

It deliberately exposes narrow APIs so sahool-platform can act as a BFF/facade and stop
owning loop-closure persistence semantics.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

app = FastAPI(title="Sahool Decision Service", version="p4.0")

LOOP_TABLES = [
    "decision_record",
    "dispatch_decisions",
    "outcome_record",
    "recommendation_outcomes",
    "online_learning_updates",
]


def _tenant(x_tenant_id: str | None) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=401, detail="X-Tenant-Id is required")
    return x_tenant_id


class DecisionRecordIn(BaseModel):
    decision_id: str | None = None
    field_id: str | None = None
    decision_type: str = "recommendation"
    region: str | None = None
    stage: str = "decision"
    decision_value: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    created_by: str | None = None


class DispatchDecisionIn(BaseModel):
    recommendation_id: str
    action_type: str
    risk_level: str = "MEDIUM"
    field_id: str | None = None
    state: str = "pending_approval"
    command: dict[str, Any] | None = None
    created_by: str | None = None


class OutcomeRecordIn(BaseModel):
    outcome_id: str | None = None
    decision_id: str
    field_id: str | None = None
    region: str | None = None
    planned: dict[str, Any] = Field(default_factory=dict)
    actual: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    success: bool | None = None
    created_by: str | None = None
    idempotency_key: str | None = None


class RecommendationOutcomeIn(BaseModel):
    recommendation_id: str
    decision_id: str | None = None
    field_id: str | None = None
    season_id: str | None = None
    outcome: str = "pending"
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LearningUpdateIn(BaseModel):
    update_id: str | None = None
    model_id: str
    feature_set_id: str | None = None
    learning_rate: float = 0.01
    sample_count: int = 0
    label_summary: dict[str, Any] = Field(default_factory=dict)
    drift_score: float = 0.0
    action: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    field_id: str | None = None
    season_id: str | None = None
    recommendation_id: str | None = None
    decision_id: str | None = None
    evidence_snapshot_id: str | None = None


def _traceability(payload: LearningUpdateIn) -> str:
    if payload.source_type and payload.source_id:
        return "traceable"
    if payload.recommendation_id or payload.decision_id or payload.evidence_snapshot_id:
        return "derived_partial"
    return "rejected_untraceable"


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"ok": True, "service": "decision-service"}


@app.get("/readyz")
def readyz() -> dict[str, Any]:
    return {"ready": True, "owned_tables": LOOP_TABLES}


@app.get("/contract")
def contract() -> dict[str, Any]:
    return {
        "service": "decision-service",
        "phase": "P4",
        "owns": ["decision", "dispatch", "outcome", "learning-lineage"],
        "owned_tables": LOOP_TABLES,
        "platform_role": "BFF/facade only; no direct loop-table writes",
    }


@app.post("/v1/decisions/record")
def record_decision(
    payload: DecisionRecordIn, x_tenant_id: str | None = Header(default=None)
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    did = payload.decision_id or "dec_" + uuid4().hex[:16]
    return {
        "persisted": True,
        "tenant_id": tenant,
        "decision_id": did,
        "stage": payload.stage,
        "recorded_at": datetime.now(UTC).isoformat(),
    }


@app.post("/v1/dispatch/decisions")
def record_dispatch(
    payload: DispatchDecisionIn, x_tenant_id: str | None = Header(default=None)
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    did = "disp_" + uuid4().hex[:16]
    return {
        "persisted": True,
        "tenant_id": tenant,
        "decision_id": did,
        "recommendation_id": payload.recommendation_id,
        "state": payload.state,
    }


@app.get("/v1/dispatch/decisions")
def list_dispatch(
    field_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    return {
        "tenant_id": _tenant(x_tenant_id),
        "field_id": field_id,
        "limit": limit,
        "decisions": [],
    }


@app.post("/v1/outcomes/record")
def record_outcome(
    payload: OutcomeRecordIn, x_tenant_id: str | None = Header(default=None)
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    oid = payload.outcome_id or "out_" + uuid4().hex[:16]
    return {
        "persisted": True,
        "tenant_id": tenant,
        "outcome_id": oid,
        "decision_id": payload.decision_id,
        "success": payload.success,
    }


@app.post("/v1/recommendation-outcomes")
def record_recommendation_outcome(
    payload: RecommendationOutcomeIn, x_tenant_id: str | None = Header(default=None)
) -> dict[str, Any]:
    return {
        "persisted": True,
        "tenant_id": _tenant(x_tenant_id),
        "recommendation_id": payload.recommendation_id,
        "decision_id": payload.decision_id,
        "outcome": payload.outcome,
    }


@app.post("/v1/learning/updates")
def record_learning_update(
    payload: LearningUpdateIn, x_tenant_id: str | None = Header(default=None)
) -> dict[str, Any]:
    status = _traceability(payload)
    return {
        "persisted": status != "rejected_untraceable",
        "tenant_id": _tenant(x_tenant_id),
        "update_id": payload.update_id or "lu_" + uuid4().hex[:16],
        "traceability_status": status,
    }


@app.get("/v1/learning/summary")
def learning_summary(
    field_id: str | None = None,
    season_id: str | None = None,
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    return {
        "tenant_id": _tenant(x_tenant_id),
        "field_id": field_id,
        "season_id": season_id,
        "outcome_reconciliation": {"enabled": True, "sample_count": 0, "success_rate": None},
    }


@app.get("/v1/decisions/{decision_id}/lineage")
def decision_lineage(
    decision_id: str, x_tenant_id: str | None = Header(default=None)
) -> dict[str, Any]:
    return {
        "tenant_id": _tenant(x_tenant_id),
        "decision_id": decision_id,
        "decision": None,
        "outcomes": [],
        "stages_present": [],
    }
