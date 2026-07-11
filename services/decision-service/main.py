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

import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from cutover import readiness_from_env
from fastapi import FastAPI, Header, HTTPException, Query
from persistence import (
    list_decision_records,
    list_review_queue,
    persist_decision_record,
    persist_dispatch_decision,
    persist_learning_update,
    persist_outcome_record,
    persist_recommendation_outcome,
    review_decision,
    create_execution_plan,
    authorize_dispatch,
    create_execution_request,
    claim_execution_request,
    record_execution_receipt,
    verify_execution_outcome,
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
    "decision_reviews",
    "decision_execution_plans",
    "decision_dispatch_authorizations",
    "decision_execution_requests",
    "decision_execution_delivery_attempts",
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


logger = logging.getLogger("decision-service")


def _database_configured() -> bool:
    return bool(os.getenv("DATABASE_URL", "").strip())


async def _db_readiness() -> dict[str, Any]:
    """Read-only DB readiness probe for the SoR-promotion cutover.

    When a DATABASE_URL is configured this proves the DB is reachable and every migration
    (001 + 002, including the WX-10.7 review layer) is applied and checksum-current. It is
    defensive by construction: any failure yields a not-ready signal, never a raised exception
    — a readiness endpoint must not 500. In mirror mode (no DATABASE_URL) DB fields are null.
    """
    if not _database_configured():
        return {
            "database_configured": False,
            "db_reachable": None,
            "migrations_current": None,
            "pending_migrations": [],
        }
    try:
        from migration_runner import check_migrations

        status = await check_migrations()
        pending = list(status.get("pending", [])) + list(status.get("checksum_mismatches", []))
        return {
            "database_configured": True,
            "db_reachable": True,
            "migrations_current": bool(status.get("ok")),
            "pending_migrations": pending,
            "known_migrations": list(status.get("known_migrations", [])),
        }
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - readiness must never raise
        return {
            "database_configured": True,
            "db_reachable": False,
            "migrations_current": False,
            "pending_migrations": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def sor_misconfig_message() -> str | None:
    """Pure helper: the fail-closed warning when SoR is requested without a database, else None."""
    if sor_requested_without_db():
        return (
            "DECISION_SERVICE_SOR_ENABLED=true but DATABASE_URL is missing — refusing to claim "
            "authoritative persistence. Writes stay in fail-closed mirror mode and /readyz reports "
            "degraded until DATABASE_URL is supplied and migrations are verified."
        )
    return None


@app.on_event("startup")
async def _startup_sor_guard() -> None:
    message = sor_misconfig_message()
    if message:
        logger.error(message)


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "alive", "ok": True, "service": "decision-service"}


@app.get("/readyz")
async def readyz() -> dict[str, Any]:
    db = await _db_readiness()
    sor_on = sor_enabled()
    misconfigured = sor_requested_without_db()
    # Fail-closed readiness: SoR requested without a DB is a misconfiguration; and once SoR is on
    # the DB must be reachable with migrations current before the service is "ready".
    ready = (not misconfigured) and (
        not sor_on or bool(db["db_reachable"] and db["migrations_current"])
    )
    return {
        "status": "ready" if ready else "degraded",
        "ready": ready,
        "service": "decision-service",
        "implemented_runtime": True,
        "owned_tables": LOOP_TABLES,
        "sor_enabled": sor_on,
        "sor_requested_without_db": misconfigured,
        "mode": "system-of-record" if sor_on else "interim-mirror",
        "db_readiness": db,
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


@app.get("/v1/decisions/review-queue")
async def review_queue(
    x_tenant_id: str | None = Header(default=None),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, Any]:
    """WX-10.8 — authoritative queue of pending decision candidates.

    Mirror mode fails closed instead of returning a misleading empty queue. Tenant isolation is
    enforced by the persistence query and the tenant comes only from the trusted gateway header.
    """
    tenant = _tenant(x_tenant_id)
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record (mirror mode) — review queue unavailable",
        )
    items = await list_review_queue(tenant_id=tenant, limit=limit)
    return {
        "authoritative": True,
        "persisted": True,
        "items": items,
        "count": len(items),
    }


class DecisionReviewIn(BaseModel):
    """WX-10.7 reviewer/policy action on a pending_approval candidate."""

    action: str  # "approve" | "reject"
    reason: str = ""
    expected_state: str = "pending_approval"
    candidate_lineage_id: str
    idempotency_key: str
    policy_version: str | None = None


@app.post("/v1/decisions/{decision_id}/review")
async def review_candidate(
    decision_id: str,
    payload: DecisionReviewIn,
    x_tenant_id: str | None = Header(default=None),
    x_reviewed_by: str | None = Header(default=None),
) -> dict[str, Any]:
    """WX-10.7 — authoritative, concurrency-safe ``pending_approval -> approved|rejected``
    transition owned by decision-service. Evidence is never mutated; the review is recorded in
    the append-only ``decision_reviews`` audit + an outbox event, all in one transaction.

    Fail-closed: unknown action (422), reject with empty reason (422), stale ``expected_state``
    (409), missing reviewer (400). Under SoR the transition is authoritative; otherwise the
    service stays an honest mirror sink (``persisted: false``) and the caller must fail closed.
    """
    tenant = _tenant(x_tenant_id)
    reviewed_by = (x_reviewed_by or "").strip()
    if not reviewed_by:
        raise HTTPException(status_code=400, detail="X-Reviewed-By is required")
    if payload.action not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail="action must be 'approve' or 'reject'")
    if not payload.candidate_lineage_id:
        raise HTTPException(status_code=422, detail="candidate_lineage_id is required")
    if not payload.idempotency_key:
        raise HTTPException(status_code=422, detail="idempotency_key is required")
    if payload.action == "reject" and not payload.reason.strip():
        raise HTTPException(status_code=422, detail="reason is required to reject")
    # Optimistic concurrency: the caller asserts the state it saw. Anything other than
    # pending_approval is stale by definition (the only reviewable state).
    if payload.expected_state != "pending_approval":
        raise HTTPException(status_code=409, detail="expected_state must be pending_approval")

    if not sor_enabled():
        # A review is a state TRANSITION — unlike the mirror-able write endpoints, there is no
        # authoritative write to honestly mirror. Under the current interim-bridge/mirror
        # deployment (ownership still platform-owned, no DATABASE_URL), the transition cannot be
        # made, so we FAIL CLOSED (503) and never return a mirror ack. The endpoint becomes
        # authoritative only once SoR is deployed (DECISION_SERVICE_SOR_ENABLED + DATABASE_URL +
        # promoted ownership).
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record (mirror mode) — review "
            "unavailable until SoR cutover",
        )

    new_state = "approved" if payload.action == "approve" else "rejected"
    result = await review_decision(
        tenant_id=tenant,
        decision_id=decision_id,
        action=payload.action,
        new_state=new_state,
        reason=payload.reason,
        reviewed_by=reviewed_by,
        candidate_lineage_id=payload.candidate_lineage_id,
        idempotency_key=payload.idempotency_key,
        policy_version=payload.policy_version,
    )
    status = result.get("status")
    if status == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if status == "not_found":
        raise HTTPException(status_code=404, detail="decision candidate not found")
    # conflict: not_pending_approval / candidate_lineage_mismatch / already_reviewed /
    # idempotency_key_payload_mismatch — all 409 (concurrency/terminal-state).
    raise HTTPException(status_code=409, detail=result.get("reason", "review conflict"))


class ExecutionPlanIn(BaseModel):
    """WX-10.9 non-executing plan derived from one approved decision."""

    review_id: str
    candidate_lineage_id: str
    operation_type: str
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    target_zone_ids: list[str] = Field(default_factory=list)
    required_resources: list[dict[str, Any]] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    safety_conditions: dict[str, Any] = Field(default_factory=dict)
    weather_window_reference: dict[str, Any] | None = None
    idempotency_key: str


@app.post("/v1/decisions/{decision_id}/execution-plan")
async def build_execution_plan(
    decision_id: str,
    payload: ExecutionPlanIn,
    x_tenant_id: str | None = Header(default=None),
    x_created_by: str | None = Header(default=None),
) -> dict[str, Any]:
    """WX-10.9 approved decision -> persisted planned execution plan.

    This boundary does not authorize dispatch and never creates tasks or equipment commands.
    """
    tenant = _tenant(x_tenant_id)
    created_by = (x_created_by or "").strip()
    if not created_by:
        raise HTTPException(status_code=400, detail="X-Created-By is required")
    if not payload.review_id or not payload.candidate_lineage_id or not payload.idempotency_key:
        raise HTTPException(
            status_code=422,
            detail="review_id, candidate_lineage_id and idempotency_key are required",
        )
    if not payload.operation_type.strip():
        raise HTTPException(status_code=422, detail="operation_type is required")
    if (
        payload.planned_start
        and payload.planned_end
        and payload.planned_end <= payload.planned_start
    ):
        raise HTTPException(status_code=422, detail="planned_end must be after planned_start")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — execution planning unavailable",
        )

    result = await create_execution_plan(
        tenant_id=tenant,
        decision_id=decision_id,
        review_id=payload.review_id,
        candidate_lineage_id=payload.candidate_lineage_id,
        idempotency_key=payload.idempotency_key,
        created_by=created_by,
        payload=payload,
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="approved decision not found")
    raise HTTPException(status_code=409, detail=result.get("reason", "execution plan conflict"))


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


class DispatchAuthorizationIn(BaseModel):
    """WX-10.10 non-executing authorization for one planned execution plan."""

    decision_id: str
    review_id: str
    candidate_lineage_id: str
    expected_plan_state: str = "planned"
    policy_version: str
    weather_snapshot_id: str
    resource_snapshot_id: str
    authorization_reason: str | None = None
    idempotency_key: str


@app.post("/v1/execution-plans/{execution_plan_id}/authorize-dispatch")
async def authorize_execution_plan_dispatch(
    execution_plan_id: str,
    payload: DispatchAuthorizationIn,
    x_tenant_id: str | None = Header(default=None),
    x_authorized_by: str | None = Header(default=None),
) -> dict[str, Any]:
    """WX-10.10 planned execution plan -> persisted dispatch authorization.

    This boundary records authorization only. It never dispatches, creates a task, or sends an
    equipment/actuator command.
    """
    tenant = _tenant(x_tenant_id)
    authorized_by = (x_authorized_by or "").strip()
    if not authorized_by:
        raise HTTPException(status_code=400, detail="X-Authorized-By is required")
    required = {
        "decision_id": payload.decision_id,
        "review_id": payload.review_id,
        "candidate_lineage_id": payload.candidate_lineage_id,
        "policy_version": payload.policy_version,
        "weather_snapshot_id": payload.weather_snapshot_id,
        "resource_snapshot_id": payload.resource_snapshot_id,
        "idempotency_key": payload.idempotency_key,
    }
    missing = [name for name, value in required.items() if not str(value or "").strip()]
    if missing:
        raise HTTPException(
            status_code=422, detail=f"required fields missing: {', '.join(missing)}"
        )
    if payload.expected_plan_state != "planned":
        raise HTTPException(status_code=409, detail="expected_plan_state must be planned")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — dispatch authorization unavailable",
        )

    result = await authorize_dispatch(
        tenant_id=tenant,
        execution_plan_id=execution_plan_id,
        decision_id=payload.decision_id,
        review_id=payload.review_id,
        candidate_lineage_id=payload.candidate_lineage_id,
        idempotency_key=payload.idempotency_key,
        authorized_by=authorized_by,
        payload=payload,
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="execution plan not found")
    raise HTTPException(
        status_code=409, detail=result.get("reason", "dispatch authorization conflict")
    )


class ExecutionRequestIn(BaseModel):
    dispatch_authorization_id: str
    execution_plan_id: str
    decision_id: str
    target_type: str
    target_id: str
    operation_type: str
    command_payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


@app.post("/v1/dispatch-authorizations/{dispatch_authorization_id}/execute")
async def execute_authorized_dispatch(
    dispatch_authorization_id: str,
    payload: ExecutionRequestIn,
    x_tenant_id: str | None = Header(default=None),
    x_requested_by: str | None = Header(default=None),
) -> dict[str, Any]:
    """WX-10.11a: persist a task/equipment execution request.

    This endpoint does not call MQTT or a task provider directly. It writes one authoritative
    execution request plus outbox event for a downstream adapter and fails closed outside SoR.
    """
    tenant = _tenant(x_tenant_id)
    requested_by = (x_requested_by or "").strip()
    if not requested_by:
        raise HTTPException(status_code=400, detail="X-Requested-By is required")
    if payload.dispatch_authorization_id != dispatch_authorization_id:
        raise HTTPException(status_code=409, detail="dispatch_authorization_id mismatch")
    if payload.target_type not in {"task", "equipment"}:
        raise HTTPException(status_code=422, detail="target_type must be task or equipment")
    for name in (
        "execution_plan_id",
        "decision_id",
        "target_id",
        "operation_type",
        "idempotency_key",
    ):
        if not str(getattr(payload, name, "") or "").strip():
            raise HTTPException(status_code=422, detail=f"{name} is required")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — execution unavailable",
        )
    result = await create_execution_request(
        tenant_id=tenant,
        dispatch_authorization_id=dispatch_authorization_id,
        requested_by=requested_by,
        payload=payload,
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="dispatch authorization not found")
    raise HTTPException(status_code=409, detail=result.get("reason", "execution request conflict"))


class ExecutionDeliveryClaimIn(BaseModel):
    adapter_id: str
    adapter_kind: str
    delivery_token: str


class ExecutionReceiptIn(BaseModel):
    adapter_id: str
    delivery_token: str
    receipt_id: str
    receipt_status: str
    receipt_payload: dict[str, Any] = Field(default_factory=dict)


@app.post("/v1/execution-requests/{execution_request_id}/claim")
async def claim_execution_delivery(
    execution_request_id: str,
    payload: ExecutionDeliveryClaimIn,
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """WX-10.11b: atomically claim one queued request for one downstream adapter."""
    tenant = _tenant(x_tenant_id)
    if payload.adapter_kind not in {"task", "equipment"}:
        raise HTTPException(status_code=422, detail="adapter_kind must be task or equipment")
    for name in ("adapter_id", "delivery_token"):
        if not str(getattr(payload, name, "") or "").strip():
            raise HTTPException(status_code=422, detail=f"{name} is required")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — delivery unavailable",
        )
    result = await claim_execution_request(
        tenant_id=tenant,
        execution_request_id=execution_request_id,
        adapter_id=payload.adapter_id,
        adapter_kind=payload.adapter_kind,
        delivery_token=payload.delivery_token,
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="execution request not found")
    raise HTTPException(status_code=409, detail=result.get("reason", "delivery claim conflict"))


@app.post("/v1/execution-requests/{execution_request_id}/receipt")
async def ingest_execution_receipt(
    execution_request_id: str,
    payload: ExecutionReceiptIn,
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """WX-10.11b: persist one terminal adapter receipt; no outcome/learning write occurs here."""
    tenant = _tenant(x_tenant_id)
    if payload.receipt_status not in {"accepted", "failed"}:
        raise HTTPException(status_code=422, detail="receipt_status must be accepted or failed")
    for name in ("adapter_id", "delivery_token", "receipt_id"):
        if not str(getattr(payload, name, "") or "").strip():
            raise HTTPException(status_code=422, detail=f"{name} is required")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — receipt unavailable",
        )
    result = await record_execution_receipt(
        tenant_id=tenant,
        execution_request_id=execution_request_id,
        adapter_id=payload.adapter_id,
        delivery_token=payload.delivery_token,
        receipt_id=payload.receipt_id,
        receipt_status=payload.receipt_status,
        receipt_payload=payload.receipt_payload,
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="execution delivery claim not found")
    raise HTTPException(status_code=409, detail=result.get("reason", "receipt conflict"))


class ExecutionOutcomeVerificationIn(BaseModel):
    execution_plan_id: str
    dispatch_authorization_id: str
    decision_id: str
    receipt_id: str
    verification_state: str
    evidence_snapshot_id: str
    actual: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


@app.post("/v1/execution-requests/{execution_request_id}/verify-outcome")
async def verify_terminal_execution_outcome(
    execution_request_id: str,
    payload: ExecutionOutcomeVerificationIn,
    x_tenant_id: str | None = Header(default=None),
    x_verified_by: str | None = Header(default=None),
) -> dict[str, Any]:
    """WX-10.12: convert terminal delivery evidence into one immutable canonical outcome."""
    tenant = _tenant(x_tenant_id)
    verified_by = (x_verified_by or "").strip()
    if not verified_by:
        raise HTTPException(status_code=400, detail="X-Verified-By is required")
    if payload.verification_state not in {"verified_success", "verified_failure"}:
        raise HTTPException(
            status_code=422,
            detail="verification_state must be verified_success or verified_failure",
        )
    for name in (
        "execution_plan_id",
        "dispatch_authorization_id",
        "decision_id",
        "receipt_id",
        "evidence_snapshot_id",
        "idempotency_key",
    ):
        if not str(getattr(payload, name, "") or "").strip():
            raise HTTPException(status_code=422, detail=f"{name} is required")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — outcome verification unavailable",
        )
    result = await verify_execution_outcome(
        tenant_id=tenant,
        execution_request_id=execution_request_id,
        verified_by=verified_by,
        payload=payload,
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="terminal execution request not found")
    raise HTTPException(
        status_code=409, detail=result.get("reason", "outcome verification conflict")
    )
