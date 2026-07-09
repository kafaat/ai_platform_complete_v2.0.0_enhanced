"""decision-service — INTERIM non-authoritative mirror for the decision/outcome/learning loop.

TEMPORARY BRIDGE (not the final architecture):
``sahool-platform`` is the temporary Source of Record (SoR) for the closed-loop tables
below — it performs the authoritative DB write and only then best-effort mirrors here.
By default this service remains a mirror sink and returns an honest, non-authoritative
acknowledgement (``persisted: false``). It may become authoritative only when the
explicit SoR gate is enabled: ``DECISION_SERVICE_SOR_ENABLED=true`` and
``DATABASE_URL`` is configured after migrations/backfill have been verified.

Loop tables (authoritative writer = sahool-platform for now; future SoR = decision-service):
- decision_record
- dispatch_decisions
- outcome_record
- recommendation_outcomes
- online_learning_updates

Migration path to a real decision-service SoR is documented in
``docs/architecture/DECISION_SERVICE_SOR_CUTOVER_READINESS.md`` and
``docs/runbooks/DECISION_SERVICE_SOR_CUTOVER_RUNBOOK.md``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from cutover import readiness_from_env
from fastapi import FastAPI, Header, HTTPException, Query
from persistence import (
    list_decision_records,
    persist_decision_record,
    persist_dispatch_decision,
    persist_learning_update,
    persist_outcome_record,
    persist_recommendation_outcome,
    sor_enabled,
    sor_requested_without_db,
)
from pydantic import BaseModel, Field

app = FastAPI(title="Sahool Decision Service", version="p0-sor-strangler")

LOOP_TABLES = [
    "decision_record",
    "dispatch_decisions",
    "outcome_record",
    "recommendation_outcomes",
    "online_learning_updates",
]

# Honest mirror-sink contract: this service is NOT the system-of-record yet. Write
# endpoints acknowledge receipt without claiming persistence — the platform already
# performed the authoritative write before mirroring here.
_MIRROR_NOTE = (
    "mirror-only; decision-service is not yet the system-of-record "
    "(sahool-platform is the temporary Source of Record and already persisted this write)"
)


def _mirror_ack(**extra: Any) -> dict[str, Any]:
    """Truthful acknowledgement for a non-authoritative mirror sink (never persisted:true)."""
    return {
        "accepted": True,
        "authoritative": False,
        "persisted": False,
        "note": _MIRROR_NOTE,
        **extra,
    }


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
    return {"status": "alive", "ok": True, "service": "decision-service"}


@app.get("/readyz")
def readyz() -> dict[str, Any]:
    ready = not sor_requested_without_db()
    return {
        "status": "ready" if ready else "degraded",
        "ready": ready,
        "service": "decision-service",
        "implemented_runtime": True,
        "owned_tables": LOOP_TABLES,
        "sor_enabled": sor_enabled(),
        "mode": "system-of-record" if sor_enabled() else "interim-mirror",
    }


@app.get("/v1/cutover/readiness")
def cutover_readiness() -> dict[str, Any]:
    """Fail-closed SoR promotion status.

    This endpoint is intentionally stricter than `/readyz`: setting
    DECISION_SERVICE_SOR_ENABLED alone is not enough to demote sahool-platform.
    """
    return readiness_from_env().as_dict()


@app.get("/contract")
def contract() -> dict[str, Any]:
    return {
        "service": "decision-service",
        "contract_version": "2026-07-09.sor-strangler",
        "implemented_runtime": True,
        "phase": "P0-SOR-strangler",
        "role": (
            "system-of-record when DECISION_SERVICE_SOR_ENABLED=true and DATABASE_URL is set; "
            "otherwise honest non-authoritative best-effort mirror"
        ),
        "authoritative": sor_enabled(),
        "system_of_record": "decision-service" if sor_enabled() else "sahool-platform (temporary)",
        "mirrors_tables": LOOP_TABLES,
        "owns_tables_when_promoted": LOOP_TABLES,
        "platform_role": (
            "before cutover: sahool-platform is the temporary Source of Record and mirrors here; "
            "after cutover: sahool-platform becomes orchestrator/BFF and decision-service persists"
        ),
        "persistence_gate": "DECISION_SERVICE_SOR_ENABLED=true + DATABASE_URL",
        "cutover_readiness_endpoint": "/v1/cutover/readiness",
        "demotion_gate": "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED=true",
        "outbox": "decision_outbox_events",
        "note": "SoR disabled: " + _MIRROR_NOTE
        if not sor_enabled()
        else "decision-service persistence enabled",
        "migration_path": (
            "apply services/decision-service/migrations/001_decision_sor.sql, run real Postgres "
            "integration tests, backfill from the platform SoR, then enable DECISION_SERVICE_SOR_ENABLED"
        ),
    }


@app.post("/v1/decisions/record")
async def record_decision(
    payload: DecisionRecordIn, x_tenant_id: str | None = Header(default=None)
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    did = payload.decision_id or "dec_" + uuid4().hex[:16]
    if sor_enabled():
        await persist_decision_record(tenant_id=tenant, payload=payload, decision_id=did)
        return {
            "accepted": True,
            "authoritative": True,
            "persisted": True,
            "tenant_id": tenant,
            "decision_id": did,
            "stage": payload.stage,
            "outbox": "decision_outbox_events",
            "received_at": datetime.now(UTC).isoformat(),
        }
    return _mirror_ack(
        tenant_id=tenant,
        decision_id=did,
        stage=payload.stage,
        received_at=datetime.now(UTC).isoformat(),
    )


@app.post("/v1/dispatch/decisions")
async def record_dispatch(
    payload: DispatchDecisionIn, x_tenant_id: str | None = Header(default=None)
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    did = "disp_" + uuid4().hex[:16]
    if sor_enabled():
        await persist_dispatch_decision(tenant_id=tenant, payload=payload, decision_id=did)
        return {
            "accepted": True,
            "authoritative": True,
            "persisted": True,
            "tenant_id": tenant,
            "decision_id": did,
            "recommendation_id": payload.recommendation_id,
            "state": payload.state,
            "outbox": "decision_outbox_events",
        }
    return _mirror_ack(
        tenant_id=tenant,
        decision_id=did,
        recommendation_id=payload.recommendation_id,
        state=payload.state,
    )


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
async def record_outcome(
    payload: OutcomeRecordIn, x_tenant_id: str | None = Header(default=None)
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    oid = payload.outcome_id or "out_" + uuid4().hex[:16]
    if sor_enabled():
        await persist_outcome_record(tenant_id=tenant, payload=payload, outcome_id=oid)
        return {
            "accepted": True,
            "authoritative": True,
            "persisted": True,
            "tenant_id": tenant,
            "outcome_id": oid,
            "decision_id": payload.decision_id,
            "success": payload.success,
            "outbox": "decision_outbox_events",
        }
    return _mirror_ack(
        tenant_id=tenant,
        outcome_id=oid,
        decision_id=payload.decision_id,
        success=payload.success,
    )


@app.post("/v1/recommendation-outcomes")
async def record_recommendation_outcome(
    payload: RecommendationOutcomeIn, x_tenant_id: str | None = Header(default=None)
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    if sor_enabled():
        await persist_recommendation_outcome(tenant_id=tenant, payload=payload)
        return {
            "accepted": True,
            "authoritative": True,
            "persisted": True,
            "tenant_id": tenant,
            "recommendation_id": payload.recommendation_id,
            "decision_id": payload.decision_id,
            "outcome": payload.outcome,
            "outbox": "decision_outbox_events",
        }
    return _mirror_ack(
        tenant_id=tenant,
        recommendation_id=payload.recommendation_id,
        decision_id=payload.decision_id,
        outcome=payload.outcome,
    )


@app.post("/v1/learning/updates")
async def record_learning_update(
    payload: LearningUpdateIn, x_tenant_id: str | None = Header(default=None)
) -> dict[str, Any]:
    status = _traceability(payload)
    tenant = _tenant(x_tenant_id)
    update_id = payload.update_id or "lu_" + uuid4().hex[:16]
    if sor_enabled():
        if status == "rejected_untraceable":
            raise HTTPException(status_code=422, detail="learning update must be traceable")
        await persist_learning_update(
            tenant_id=tenant, payload=payload, update_id=update_id, traceability_status=status
        )
        return {
            "accepted": True,
            "authoritative": True,
            "persisted": True,
            "tenant_id": tenant,
            "update_id": update_id,
            "traceability_status": status,
            "outbox": "decision_outbox_events",
        }
    # Traceability is still validated and echoed back (a useful mirror check), but this
    # sink does not persist — ``persisted`` stays false regardless of traceability.
    return _mirror_ack(
        tenant_id=tenant,
        update_id=update_id,
        traceability_status=status,
    )


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


@app.get("/v1/decisions")
async def list_decisions(
    field_id: str | None = None,
    decision_type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    if sor_enabled():
        data = await list_decision_records(
            tenant_id=tenant, field_id=field_id, decision_type=decision_type, limit=limit
        )
        return {
            "tenant_id": tenant,
            "field_id": field_id,
            "decision_type": decision_type,
            "limit": limit,
            **data,
        }
    return {
        "tenant_id": tenant,
        "field_id": field_id,
        "decision_type": decision_type,
        "limit": limit,
        "decisions": [],
        "count": 0,
    }


@app.get("/v1/fields/{field_id}/lineage")
def field_lineage(
    field_id: str,
    limit: int = Query(50, ge=1, le=200),
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    return {
        "tenant_id": _tenant(x_tenant_id),
        "field_id": field_id,
        "limit": limit,
        "decisions": [],
        "orphan_outcomes": [],
        "count": 0,
    }


@app.get("/v1/outcomes/reconciled")
def reconciled_outcomes(
    field_id: str | None = None,
    season_id: str | None = None,
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    return {
        "tenant_id": _tenant(x_tenant_id),
        "field_id": field_id,
        "season_id": season_id,
        "outcome_reconciliation": {
            "enabled": True,
            "sample_count": 0,
            "success_rate": None,
            "by_source": {},
            "by_kind": {},
        },
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
