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

import hmac
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import activation_gate
import satellite_cdse_activation_gate
from agronomic_context.contracts import ContextComposeIn  # noqa: E402
from cutover import readiness_from_env
from fastapi import FastAPI, Header, HTTPException, Query
from persistence import (
    authorize_dispatch,
    build_calibration_dataset,
    claim_execution_request,
    claim_model_registry_activation_command,
    claim_model_registry_rollback_command,
    compose_agronomic_context,
    create_execution_plan,
    create_execution_request,
    create_learning_attribution,
    create_model_activation_request,
    create_model_evaluation_run,
    create_model_promotion_decision,
    create_model_registry_rollback_command,
    create_post_activation_verification,
    create_retraining_request,
    create_rollout_plan,
    create_runtime_schedule,
    get_active_model_state,
    get_context_snapshot,
    get_decision_agronomic_evidence,
    list_decision_records,
    list_inflight_execution_requests,
    list_queued_execution_requests,
    list_review_queue,
    list_runtime_work,
    list_worker_tenants,
    persist_decision_record,
    persist_dispatch_decision,
    persist_learning_update,
    persist_outcome_record,
    persist_recommendation_outcome,
    persist_vegetation_snapshot,
    record_execution_receipt,
    record_model_registry_activation_receipt,
    record_model_registry_rollback_receipt,
    record_monitoring_snapshot,
    record_reconcile_evidence,
    record_reservation_dispatch_intent,
    record_retraining_dispatch_receipt,
    record_rollout_receipt,
    register_runtime_worker_tenant,
    review_decision,
    review_model_activation_request,
    sor_enabled,
    sor_requested_without_db,
    strict_worker_tenants_enabled,
    verify_execution_outcome,
    worker_tenant_authorized,
)
from pydantic import BaseModel, ConfigDict, Field

from shared.contracts.soil import validate_soil_use


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Modern FastAPI lifespan startup (replaces the deprecated startup event handler).
    # sor_misconfig_message()/logger are module globals resolved at startup time.
    # Container-audit V21 §4.1: hard fail-closed — refuse to start an unauthenticated
    # decision service in production (never log the token itself, only its absence).
    auth_error = production_auth_startup_error()
    if auth_error:
        logger.error(auth_error)
        raise RuntimeError(auth_error)
    message = sor_misconfig_message()
    if message:
        logger.error(message)
    yield


app = FastAPI(title="Sahool Decision Service", version="p0-sor-strangler", lifespan=lifespan)

# Critical: do not trust identity headers (X-Tenant-Id / X-*-By) on the raw internal port.
# When DECISION_SERVICE_AUTH_TOKEN is configured, every non-probe request must present the shared
# service bearer token (the runtime/worker already send it). Unset (dev/mirror) → no-op, so the
# existing gateway-trusted flow is unchanged. This is defense-in-depth for the future SoR mode:
# a service reachable directly inside the cluster can no longer spoof tenant/actor identities.
_AUTH_EXEMPT = {"/healthz", "/readyz", "/livez", "/", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def _service_token_guard(request, call_next):
    required = os.getenv("DECISION_SERVICE_AUTH_TOKEN", "").strip()
    if required and request.url.path not in _AUTH_EXEMPT:
        header = request.headers.get("authorization", "")
        presented = header[7:].strip() if header[:7].lower() == "bearer " else ""
        if not presented or not hmac.compare_digest(presented, required):
            from fastapi.responses import JSONResponse

            return JSONResponse({"detail": "unauthorized: service token required"}, status_code=401)
    return await call_next(request)


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
    "decision_learning_attributions",
    "decision_model_evaluation_runs",
    "decision_model_promotion_decisions",
    "decision_model_activation_requests",
    "decision_model_activation_reviews",
    "decision_model_registry_activation_commands",
    "decision_model_registry_activation_claims",
    "decision_model_registry_activation_receipts",
    "decision_model_registry_rollback_commands",
    "decision_model_registry_rollback_claims",
    "decision_model_registry_rollback_receipts",
    "decision_model_post_activation_verifications",
    "decision_model_rollout_plans",
    "decision_model_monitoring_snapshots",
    "decision_model_retraining_requests",
    "decision_model_rollout_receipts",
    "decision_model_retraining_dispatch_receipts",
    "decision_model_runtime_work_claims",
    "decision_model_runtime_schedules",
    "decision_model_reconcile_evidence",
    "decision_agronomic_context_snapshots",
    "decision_field_historical_context_snapshots",
    "decision_feature_manifests",
    "decision_feature_manifest_entries",
    "decision_vegetation_snapshots",
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
    # AC-1 context lineage: optional until enforcement is enabled, always validated when present.
    agronomic_context_snapshot_id: str | None = None
    field_historical_context_snapshot_id: str | None = None
    feature_manifest_id: str | None = None
    # AC-6 direct agronomic lineage: identity columns + immutable vegetation evidence +
    # the client-claimed manifest hash (checked against the stored manifest content hash).
    season_id: str | None = None
    crop_id: str | None = None
    cultivar_id: str | None = None
    vegetation_snapshot_id: str | None = None
    feature_manifest_hash: str | None = None


class VegetationSnapshotIn(BaseModel):
    """AC-6 immutable vegetation evidence: content-addressed by snapshot_hash (the hash IS the
    idempotency key — a replay returns the canonical existing snapshot, never a duplicate)."""

    snapshot_id: str | None = None
    field_id: str
    season_id: str | None = None
    contract_version: str = "vegetation-snapshot.v2"
    snapshot_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-fA-F0-9]{64}$")
    acquisition_at: datetime
    data_available_at: datetime
    quality_gate: dict[str, Any]
    feature_manifest: dict[str, Any]
    payload: dict[str, Any]


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


def auth_token_missing_in_sor() -> bool:
    """Forensic F-09: authoritative mode must not run open on the internal port.

    Staged flag DECISION_REQUIRE_AUTH_TOKEN (the operator production checklist turns it
    on): when set, SoR mode with no DECISION_SERVICE_AUTH_TOKEN configured makes /readyz
    report degraded — orchestrators withhold traffic instead of serving an unauthenticated
    system of record.
    """
    require = os.getenv("DECISION_REQUIRE_AUTH_TOKEN", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return require and sor_enabled() and not os.getenv("DECISION_SERVICE_AUTH_TOKEN", "").strip()


def _is_production() -> bool:
    return os.getenv("SAHOOL_ENV", "development").strip().lower() in {"production", "prod"}


def production_auth_startup_error() -> str | None:
    """Container-audit V21 §4.1: authentication is mandatory in production — refuse to start.

    In production (SAHOOL_ENV=production), DECISION_SERVICE_AUTH_TOKEN must be configured;
    without it a service reachable directly on the internal port can spoof tenant/actor
    identity headers (see the _service_token_guard middleware). Rather than start open and
    degrade /readyz (the earlier staged behaviour), we hard-fail startup so an unauthenticated
    authoritative service can never accept traffic. An explicit DECISION_REQUIRE_AUTH_TOKEN
    also arms the check outside production. Returns the fail message, or None when satisfied.
    """
    require = os.getenv("DECISION_REQUIRE_AUTH_TOKEN", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if (require or _is_production()) and not os.getenv("DECISION_SERVICE_AUTH_TOKEN", "").strip():
        return (
            "DECISION_SERVICE_AUTH_TOKEN is required in production (or when "
            "DECISION_REQUIRE_AUTH_TOKEN is set) but is empty — refusing to start an "
            "unauthenticated decision service on the internal port. Configure the shared "
            "service bearer token before deployment."
        )
    return None


def sor_misconfig_message() -> str | None:
    """Pure helper: the fail-closed warning when SoR is requested without a database, else None."""
    if sor_requested_without_db():
        return (
            "DECISION_SERVICE_SOR_ENABLED=true but DATABASE_URL is missing — refusing to claim "
            "authoritative persistence. Writes stay in fail-closed mirror mode and /readyz reports "
            "degraded until DATABASE_URL is supplied and migrations are verified."
        )
    return None


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "alive", "ok": True, "service": "decision-service"}


@app.get("/readyz")
async def readyz() -> dict[str, Any]:
    db = await _db_readiness()
    sor_on = sor_enabled()
    misconfigured = sor_requested_without_db()
    auth_missing = auth_token_missing_in_sor()
    # Fail-closed readiness: SoR requested without a DB is a misconfiguration; once SoR is on
    # the DB must be reachable with migrations current; and (F-09, staged) an authoritative
    # service without its bearer token configured is NOT ready.
    ready = (
        (not misconfigured)
        and (not auth_missing)
        and (not sor_on or bool(db["db_reachable"] and db["migrations_current"]))
    )
    return {
        "status": "ready" if ready else "degraded",
        "ready": ready,
        "service": "decision-service",
        "implemented_runtime": True,
        "owned_tables": LOOP_TABLES,
        "sor_enabled": sor_on,
        "sor_requested_without_db": misconfigured,
        "auth_token_missing_in_sor": auth_missing,
        "enforcement": {
            "auth_token_configured": bool(os.getenv("DECISION_SERVICE_AUTH_TOKEN", "").strip()),
            "strict_worker_tenants": strict_worker_tenants_enabled(),
            "canonical_soil_profile_required": (
                os.getenv("DECISION_REQUIRE_SOIL_PROFILE", "").strip().lower()
                in {"1", "true", "yes", "on"}
                or os.getenv("SAHOOL_ENV", "development").strip().lower() == "production"
            ),
        },
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


@app.post("/v1/evidence/vegetation-snapshots")
async def create_vegetation_snapshot(
    payload: VegetationSnapshotIn, x_tenant_id: str | None = Header(default=None)
) -> dict[str, Any]:
    """AC-6: authoritative immutable vegetation-evidence writer (fail-closed in mirror mode)."""
    tenant = _tenant(x_tenant_id)
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not authoritative")
    sid = payload.snapshot_id or "veg_" + uuid4().hex[:20]
    result = await persist_vegetation_snapshot(tenant_id=tenant, payload=payload, snapshot_id=sid)
    return {
        "persisted": True,
        "snapshot_id": result["snapshot_id"],
        "created": result["created"],
        "snapshot_hash": payload.snapshot_hash,
    }


@app.post("/v1/decisions/record")
async def record_decision(
    payload: DecisionRecordIn, x_tenant_id: str | None = Header(default=None)
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    did = payload.decision_id or "dec_" + uuid4().hex[:16]
    # AC-1/AC-6 mandatory binding: when enforcement is on, no new governed decision may enter
    # without the full agronomic lineage (identity + three immutable context references +
    # vegetation evidence + manifest hash). Checked before the SoR branch: strict mode is a
    # contract violation regardless of mirror/authoritative state.
    require_ctx = os.getenv("DECISION_REQUIRE_AGRONOMIC_CONTEXT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if require_ctx:
        required = {
            "field_id": payload.field_id,
            "season_id": payload.season_id,
            "crop_id": payload.crop_id,
            "cultivar_id": payload.cultivar_id,
            "agronomic_context_snapshot_id": payload.agronomic_context_snapshot_id,
            "field_historical_context_snapshot_id": payload.field_historical_context_snapshot_id,
            "feature_manifest_id": payload.feature_manifest_id,
            "feature_manifest_hash": payload.feature_manifest_hash,
            "vegetation_snapshot_id": payload.vegetation_snapshot_id,
        }
        missing = sorted(k for k, v in required.items() if not v)
        if missing:
            raise HTTPException(
                status_code=422,
                detail={"code": "agronomic_context_required", "missing": missing},
            )
    if sor_enabled():
        result = await persist_decision_record(tenant_id=tenant, payload=payload, decision_id=did)
        if isinstance(result, dict) and result.get("status") == "rejected":
            raise HTTPException(status_code=422, detail=result.get("reason", "context rejected"))
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
    # Soil evidence gate: soil-sensitive dispatches require a sufficient canonical soil
    # profile (default-off in dev; always on in production). Fail-closed 422 when insufficient.
    command = payload.command or {}
    soil_sensitive_use = str(command.get("soil_use") or payload.action_type or "").strip().lower()
    soil_profile = command.get("soil_profile")
    require_soil_dispatch = (
        os.getenv("DECISION_REQUIRE_SOIL_EVIDENCE_GATE", "").strip().lower()
        in {"1", "true", "yes", "on"}
        or os.getenv("SAHOOL_ENV", "development").strip().lower() == "production"
    )
    soil_actions = {
        "fertilizer_rate",
        "gypsum_rate",
        "leaching_requirement",
        "subsurface_drainage_design",
        "high_risk_reclamation",
        "automatic_irrigation_execution",
        "irrigation_schedule",
        "crop_selection",
        "salinity_management_guidance",
    }
    if require_soil_dispatch and soil_sensitive_use in soil_actions:
        gate = validate_soil_use(soil_profile, soil_sensitive_use)
        if not gate.allowed:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": gate.code,
                    "reasons": list(gate.reasons),
                    "required_rank": gate.required_rank,
                    "actual_rank": gate.actual_rank,
                },
            )
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


@app.get("/v1/decisions/{decision_id}/agronomic-evidence")
async def decision_agronomic_evidence(
    decision_id: str, x_tenant_id: str | None = Header(default=None)
) -> dict[str, Any]:
    """Phase E: authoritative read of the decision's full agronomic evidence chain.

    Fail-closed: evidence is only meaningful from the system of record — mirror mode
    returns 503 instead of an empty payload that could be mistaken for "no evidence".
    """
    tenant = _tenant(x_tenant_id)
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    result = await get_decision_agronomic_evidence(tenant_id=tenant, decision_id=decision_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="decision not found")
    return {"tenant_id": tenant, "decision_id": decision_id, **result}


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


class ReservationDispatchIntentIn(BaseModel):
    source_event_id: str
    event_type: str
    evaluation_id: str | None = None
    reservation_ids: list[str] = Field(default_factory=list)
    execution_ref_type: str | None = None
    execution_ref_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


@app.post("/v1/reservation-dispatch-intents")
async def ingest_reservation_dispatch_intent(
    payload: ReservationDispatchIntentIn,
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """IRR-F01 Gate B-delivery (thin inbox): durably record a reservation dispatch INTENT
    delivered from the platform outbox. Idempotent on (tenant, source_event_id). This records
    DELIVERY only — it does NOT create an execution_request (fulfillment is a later WX-10-gated
    step). Fails closed (503) outside SoR mode, like the other execution-chain writers."""
    tenant = _tenant(x_tenant_id)
    if not str(payload.source_event_id or "").strip():
        raise HTTPException(status_code=422, detail="source_event_id is required")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — dispatch-intent inbox unavailable",
        )
    # Enforcement point (opt-in): when IRR_F01_RESERVATION_ENFORCE_ACTIVATION is on, the
    # irr_f01_reservation activation gate must be effectively enabled for this environment or the
    # intent is refused (403). Off by default so pre-activation behaviour is unchanged.
    if _enforce_reservation_activation():
        try:
            await activation_gate.enforce_enabled(_activation_environment())
        except activation_gate.ActivationNotEnabled as exc:
            raise HTTPException(
                status_code=403, detail=f"irr_f01_reservation not activated: {exc.reason}"
            ) from exc
    result = await record_reservation_dispatch_intent(
        tenant_id=tenant,
        source_event_id=payload.source_event_id,
        event_type=payload.event_type,
        payload=payload,
    )
    status = result.get("status")
    if status in ("received", "failure_notice", "duplicate"):
        return {"accepted": True, "tenant_id": tenant, **result}
    raise HTTPException(status_code=409, detail=result.get("reason", "dispatch intent conflict"))


# --- IRR-F01 Phase 1: irr_f01_reservation activation gate (operator + probe surface) ----------


def _activation_environment() -> str:
    return (
        os.getenv("ACTIVATION_ENVIRONMENT_ID") or os.getenv("SAHOOL_ENV", "development")
    ).strip()


def _enforce_reservation_activation() -> bool:
    return os.getenv("IRR_F01_RESERVATION_ENFORCE_ACTIVATION", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _activation_actor(x_requested_by: str | None) -> str:
    actor = (x_requested_by or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="X-Requested-By is required")
    return actor


class ActivationCompleteIn(BaseModel):
    # Gate-Trust-1: the caller submits RECEIPT REFERENCES only — never check results. A stray
    # ``evidence`` (or any other) field is REJECTED (422), not silently ignored — raw caller
    # evidence is forbidden, structurally.
    model_config = ConfigDict(extra="forbid")
    expected_generation: int
    evidence_refs: list[str] = Field(default_factory=list)
    ttl_seconds: int = 3600


class ActivationRevokeIn(BaseModel):
    reason: str


class ActivationEvidenceReceiptIn(BaseModel):
    """A trusted producer issues one evidence receipt over the authenticated ingest path. The server
    validates the producer identity + contract and computes the content hash — the receipt, not this
    request, becomes the source of truth the gate later resolves by id."""

    producer: str
    check_name: str
    result: str
    observed_at: str
    valid_until: str
    provenance: str | None = None
    build_sha: str | None = None
    signature: str | None = None
    key_id: str | None = None


def _activation_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") == "conflict":
        raise HTTPException(status_code=409, detail=result.get("reason", "activation conflict"))
    return {"environment_id": _activation_environment(), **result}


@app.post("/v1/activation/irr_f01_reservation/begin")
async def activation_begin(x_requested_by: str | None = Header(default=None)) -> dict[str, Any]:
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    return _activation_result(
        await activation_gate.begin_evaluation(
            _activation_environment(), actor=_activation_actor(x_requested_by)
        )
    )


@app.post("/v1/activation/irr_f01_reservation/complete")
async def activation_complete(
    payload: ActivationCompleteIn, x_requested_by: str | None = Header(default=None)
) -> dict[str, Any]:
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    return _activation_result(
        await activation_gate.complete_evaluation(
            _activation_environment(),
            expected_generation=payload.expected_generation,
            evidence_refs=payload.evidence_refs,
            actor=_activation_actor(x_requested_by),
            ttl_seconds=payload.ttl_seconds,
        )
    )


@app.post("/v1/activation/irr_f01_reservation/evidence-receipts")
async def activation_evidence_receipt(
    payload: ActivationEvidenceReceiptIn, x_requested_by: str | None = Header(default=None)
) -> dict[str, Any]:
    """Authenticated ingest for a trusted producer to issue an irr_f01_reservation evidence receipt.
    The gate validates producer identity + contract server-side and stores an append-only receipt;
    the operator later references it by id — the caller never supplies check results."""
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    result = await activation_gate.record_receipt(
        environment_id=_activation_environment(),
        producer=payload.producer,
        check_name=payload.check_name,
        result=payload.result,
        observed_at=payload.observed_at,
        valid_until=payload.valid_until,
        provenance=payload.provenance,
        build_sha=payload.build_sha,
        signature=payload.signature,
        key_id=payload.key_id,
    )
    if result.get("status") == "rejected":
        raise HTTPException(status_code=422, detail=result.get("reason", "receipt rejected"))
    return {"environment_id": _activation_environment(), **result}


@app.post("/v1/activation/irr_f01_reservation/revoke")
async def activation_revoke(
    payload: ActivationRevokeIn, x_requested_by: str | None = Header(default=None)
) -> dict[str, Any]:
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    return _activation_result(
        await activation_gate.revoke(
            _activation_environment(),
            actor=_activation_actor(x_requested_by),
            reason=payload.reason,
        )
    )


@app.post("/v1/activation/irr_f01_reservation/reset")
async def activation_reset(x_requested_by: str | None = Header(default=None)) -> dict[str, Any]:
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    return _activation_result(
        await activation_gate.reset(
            _activation_environment(), actor=_activation_actor(x_requested_by)
        )
    )


@app.get("/v1/activation/irr_f01_reservation")
async def activation_current() -> dict[str, Any]:
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    return await activation_gate.current_cached(_activation_environment())


@app.get("/v1/activation/irr_f01_reservation/probe")
async def activation_probe(
    x_activation_role: str | None = Header(default=None),
    x_activation_probe_signature: str | None = Header(default=None),
) -> dict[str, Any]:
    """Read-only probe — allowed ONLY with the activation_probe role AND a valid HMAC signature,
    never from a normal request path."""
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    try:
        return await activation_gate.probe_state(
            _activation_environment(),
            caller_role=(x_activation_role or "").strip(),
            signature=(x_activation_probe_signature or "").strip(),
        )
    except activation_gate.ActivationProbeDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


# --- Phase 2: satellite_cdse activation gate (operator + probe + source-selection surface) -----
# Symmetric with the irr_f01_reservation gate above but a SEPARATE gate module; the enforcement
# read is /source (imagery source selection), not a 403.


def _cdse_activation_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") == "conflict":
        raise HTTPException(status_code=409, detail=result.get("reason", "activation conflict"))
    return {"environment_id": _activation_environment(), **result}


@app.post("/v1/activation/satellite_cdse/begin")
async def cdse_activation_begin(
    x_requested_by: str | None = Header(default=None),
) -> dict[str, Any]:
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    return _cdse_activation_result(
        await satellite_cdse_activation_gate.begin_evaluation(
            _activation_environment(), actor=_activation_actor(x_requested_by)
        )
    )


@app.post("/v1/activation/satellite_cdse/complete")
async def cdse_activation_complete(
    payload: ActivationCompleteIn, x_requested_by: str | None = Header(default=None)
) -> dict[str, Any]:
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    return _cdse_activation_result(
        await satellite_cdse_activation_gate.complete_evaluation(
            _activation_environment(),
            expected_generation=payload.expected_generation,
            evidence_refs=payload.evidence_refs,
            actor=_activation_actor(x_requested_by),
            ttl_seconds=payload.ttl_seconds,
        )
    )


@app.post("/v1/activation/satellite_cdse/evidence-receipts")
async def cdse_activation_evidence_receipt(
    payload: ActivationEvidenceReceiptIn, x_requested_by: str | None = Header(default=None)
) -> dict[str, Any]:
    """Authenticated ingest for a trusted producer (raster-service) to issue a satellite_cdse
    evidence receipt; the operator later references it by id (never supplies check results)."""
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    result = await satellite_cdse_activation_gate.record_receipt(
        environment_id=_activation_environment(),
        producer=payload.producer,
        check_name=payload.check_name,
        result=payload.result,
        observed_at=payload.observed_at,
        valid_until=payload.valid_until,
        provenance=payload.provenance,
        build_sha=payload.build_sha,
        signature=payload.signature,
        key_id=payload.key_id,
    )
    if result.get("status") == "rejected":
        raise HTTPException(status_code=422, detail=result.get("reason", "receipt rejected"))
    return {"environment_id": _activation_environment(), **result}


@app.post("/v1/activation/satellite_cdse/revoke")
async def cdse_activation_revoke(
    payload: ActivationRevokeIn, x_requested_by: str | None = Header(default=None)
) -> dict[str, Any]:
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    return _cdse_activation_result(
        await satellite_cdse_activation_gate.revoke(
            _activation_environment(),
            actor=_activation_actor(x_requested_by),
            reason=payload.reason,
        )
    )


@app.post("/v1/activation/satellite_cdse/reset")
async def cdse_activation_reset(
    x_requested_by: str | None = Header(default=None),
) -> dict[str, Any]:
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    return _cdse_activation_result(
        await satellite_cdse_activation_gate.reset(
            _activation_environment(), actor=_activation_actor(x_requested_by)
        )
    )


@app.get("/v1/activation/satellite_cdse")
async def cdse_activation_current() -> dict[str, Any]:
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    return await satellite_cdse_activation_gate.current_cached(_activation_environment())


@app.get("/v1/activation/satellite_cdse/source")
async def cdse_active_source() -> dict[str, Any]:
    """Enforcement read: which imagery source is active for this environment — 'cdse' when the gate
    is enabled, otherwise the safe 'element84' fallback. Never a 403 (Category A source selection)."""
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    return await satellite_cdse_activation_gate.active_imagery_source(_activation_environment())


@app.get("/v1/activation/satellite_cdse/probe")
async def cdse_activation_probe(
    x_activation_role: str | None = Header(default=None),
    x_activation_probe_signature: str | None = Header(default=None),
) -> dict[str, Any]:
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="activation gate requires the system-of-record")
    try:
        return await satellite_cdse_activation_gate.probe_state(
            _activation_environment(),
            caller_role=(x_activation_role or "").strip(),
            signature=(x_activation_probe_signature or "").strip(),
        )
    except satellite_cdse_activation_gate.ActivationProbeDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


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


@app.get("/v1/execution-requests")
async def list_execution_requests(
    state: str = Query("queued"),
    target_type: str | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """ACTUATOR-DISPATCH-CONSUMER: discovery feed for downstream delivery adapters.

    Read-only enumeration of queued requests (in-flight claims excluded); the
    atomic gate remains the claim endpoint. Only state=queued is served — this
    is a work feed, not a general query API. Mirror mode is a fail-closed 503.
    """
    tenant = _tenant(x_tenant_id)
    if state != "queued":
        raise HTTPException(status_code=422, detail="only state=queued is served by this feed")
    if target_type is not None and target_type not in {"task", "equipment"}:
        raise HTTPException(status_code=422, detail="target_type must be task or equipment")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — feed unavailable",
        )
    result = await list_queued_execution_requests(
        tenant_id=tenant, target_type=target_type, limit=limit
    )
    return {"tenant_id": tenant, "state": "queued", "target_type": target_type, **result}


@app.get("/v1/execution-requests/recovery")
async def list_execution_request_recovery(
    adapter_id: str = Query(..., min_length=1),
    target_type: str | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return this adapter's in-flight requests lacking a receipt, for restart recovery."""
    tenant = _tenant(x_tenant_id)
    if target_type is not None and target_type not in {"task", "equipment"}:
        raise HTTPException(status_code=422, detail="target_type must be task or equipment")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — recovery unavailable",
        )
    result = await list_inflight_execution_requests(
        tenant_id=tenant, adapter_id=adapter_id, target_type=target_type, limit=limit
    )
    return {"tenant_id": tenant, "adapter_id": adapter_id, "target_type": target_type, **result}


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


class LearningAttributionIn(BaseModel):
    model_id: str
    feature_set_id: str | None = None
    attribution_method: str = "verified_outcome"
    label: str
    weight: float = Field(default=1.0, gt=0, le=1.0)
    evidence_snapshot_id: str
    idempotency_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.post("/v1/outcomes/{outcome_id}/learning-attribution")
async def attribute_verified_outcome_to_learning(
    outcome_id: str,
    payload: LearningAttributionIn,
    x_tenant_id: str | None = Header(default=None),
    x_attributed_by: str | None = Header(default=None),
) -> dict[str, Any]:
    """WX-10.13: create one immutable, traceable learning attribution; no model mutation."""
    tenant = _tenant(x_tenant_id)
    attributed_by = (x_attributed_by or "").strip()
    if not attributed_by:
        raise HTTPException(status_code=400, detail="X-Attributed-By is required")
    for name in ("model_id", "label", "evidence_snapshot_id", "idempotency_key"):
        if not str(getattr(payload, name, "") or "").strip():
            raise HTTPException(status_code=422, detail=f"{name} is required")
    if payload.attribution_method != "verified_outcome":
        raise HTTPException(status_code=422, detail="attribution_method must be verified_outcome")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — learning attribution unavailable",
        )
    result = await create_learning_attribution(
        tenant_id=tenant, outcome_id=outcome_id, attributed_by=attributed_by, payload=payload
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="verified outcome not found")
    raise HTTPException(
        status_code=409, detail=result.get("reason", "learning attribution conflict")
    )


@app.get("/v1/learning/calibration-dataset")
async def get_calibration_dataset(
    model_id: str = Query(..., min_length=1),
    feature_set_id: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """WX-11.1: authoritative read-only calibration dataset; no fitting or model mutation."""
    tenant = _tenant(x_tenant_id)
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — calibration dataset unavailable",
        )
    result = await build_calibration_dataset(
        tenant_id=tenant, model_id=model_id.strip(), feature_set_id=feature_set_id, limit=limit
    )
    return {"tenant_id": tenant, **result}


class ModelEvaluationRunIn(BaseModel):
    model_id: str
    feature_set_id: str | None = None
    dataset_fingerprint: str
    dataset_count: int = Field(gt=0)
    evaluator_version: str
    baseline_metrics: dict[str, Any]
    candidate_metrics: dict[str, Any]
    candidate_artifact_uri: str
    candidate_artifact_digest: str
    artifact_format: str
    idempotency_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.post("/v1/learning/evaluation-runs")
async def register_model_evaluation_run(
    payload: ModelEvaluationRunIn,
    x_tenant_id: str | None = Header(default=None),
    x_evaluated_by: str | None = Header(default=None),
) -> dict[str, Any]:
    """WX-11.2: register immutable evaluation evidence and candidate artifact metadata only."""
    tenant = _tenant(x_tenant_id)
    evaluated_by = (x_evaluated_by or "").strip()
    if not evaluated_by:
        raise HTTPException(status_code=400, detail="X-Evaluated-By is required")
    for name in (
        "model_id",
        "dataset_fingerprint",
        "evaluator_version",
        "candidate_artifact_uri",
        "candidate_artifact_digest",
        "artifact_format",
        "idempotency_key",
    ):
        if not str(getattr(payload, name, "") or "").strip():
            raise HTTPException(status_code=422, detail=f"{name} is required")
    digest = payload.candidate_artifact_digest.lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise HTTPException(status_code=422, detail="candidate_artifact_digest must be sha256 hex")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — evaluation registration unavailable",
        )
    result = await create_model_evaluation_run(
        tenant_id=tenant, evaluated_by=evaluated_by, payload=payload
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    raise HTTPException(status_code=409, detail=result.get("reason", "evaluation run conflict"))


class ModelPromotionDecisionIn(BaseModel):
    evaluation_run_id: str
    policy_version: str
    primary_metric: str
    min_improvement: float = 0.0
    lower_is_better: bool = False
    max_regression: float = Field(default=0.0, ge=0.0)
    guardrail_metrics: list[str] = Field(default_factory=list)
    idempotency_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.post("/v1/learning/promotion-decisions")
async def register_model_promotion_decision(
    payload: ModelPromotionDecisionIn,
    x_tenant_id: str | None = Header(default=None),
    x_decided_by: str | None = Header(default=None),
) -> dict[str, Any]:
    """WX-11.3: evaluate a fixed policy and record eligibility/rejection only."""
    tenant = _tenant(x_tenant_id)
    decided_by = (x_decided_by or "").strip()
    if not decided_by:
        raise HTTPException(status_code=400, detail="X-Decided-By is required")
    for name in ("evaluation_run_id", "policy_version", "primary_metric", "idempotency_key"):
        if not str(getattr(payload, name, "") or "").strip():
            raise HTTPException(status_code=422, detail=f"{name} is required")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — promotion decision unavailable",
        )
    result = await create_model_promotion_decision(
        tenant_id=tenant, decided_by=decided_by, payload=payload
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="evaluation run not found")
    raise HTTPException(status_code=409, detail=result.get("reason", "promotion decision conflict"))


class ModelActivationRequestIn(BaseModel):
    promotion_decision_id: str
    target_environment: str
    idempotency_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.post("/v1/learning/activation-requests")
async def register_model_activation_request(
    payload: ModelActivationRequestIn,
    x_tenant_id: str | None = Header(default=None),
    x_requested_by: str | None = Header(default=None),
) -> dict[str, Any]:
    """WX-11.4: create a pending activation request only; no registry mutation."""
    tenant = _tenant(x_tenant_id)
    requested_by = (x_requested_by or "").strip()
    if not requested_by:
        raise HTTPException(status_code=400, detail="X-Requested-By is required")
    if payload.target_environment not in {"staging", "production"}:
        raise HTTPException(
            status_code=422, detail="target_environment must be staging or production"
        )
    for name in ("promotion_decision_id", "idempotency_key"):
        if not str(getattr(payload, name, "") or "").strip():
            raise HTTPException(status_code=422, detail=f"{name} is required")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — activation request unavailable",
        )
    result = await create_model_activation_request(
        tenant_id=tenant, requested_by=requested_by, payload=payload
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="promotion decision not found")
    raise HTTPException(status_code=409, detail=result.get("reason", "activation request conflict"))


class ModelActivationReviewIn(BaseModel):
    review_decision: str
    review_reason: str | None = None
    registry_alias: str | None = None
    previous_artifact_uri: str | None = None
    previous_artifact_digest: str | None = None
    idempotency_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.post("/v1/learning/activation-requests/{activation_request_id}/review")
async def review_activation_request_boundary(
    activation_request_id: str,
    payload: ModelActivationReviewIn,
    x_tenant_id: str | None = Header(default=None),
    x_reviewed_by: str | None = Header(default=None),
) -> dict[str, Any]:
    """WX-11.5: approve/reject activation; approval queues an immutable registry command only."""
    tenant = _tenant(x_tenant_id)
    reviewed_by = (x_reviewed_by or "").strip()
    if not reviewed_by:
        raise HTTPException(status_code=400, detail="X-Reviewed-By is required")
    if payload.review_decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="review_decision must be approved or rejected")
    if not payload.idempotency_key.strip():
        raise HTTPException(status_code=422, detail="idempotency_key is required")
    if payload.review_decision == "rejected" and not (payload.review_reason or "").strip():
        raise HTTPException(status_code=422, detail="review_reason is required for rejection")
    if payload.review_decision == "approved":
        for name in ("registry_alias", "previous_artifact_uri", "previous_artifact_digest"):
            if not str(getattr(payload, name, "") or "").strip():
                raise HTTPException(status_code=422, detail=f"{name} is required for approval")
        digest = str(payload.previous_artifact_digest).lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise HTTPException(
                status_code=422, detail="previous_artifact_digest must be sha256 hex"
            )
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — activation review unavailable",
        )
    result = await review_model_activation_request(
        tenant_id=tenant,
        activation_request_id=activation_request_id,
        reviewed_by=reviewed_by,
        payload=payload,
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="activation request not found")
    raise HTTPException(status_code=409, detail=result.get("reason", "activation review conflict"))


class ModelRegistryActivationClaimIn(BaseModel):
    adapter_id: str
    delivery_token: str


@app.post("/v1/learning/activation-commands/{activation_command_id}/claim")
async def claim_registry_activation_command_boundary(
    activation_command_id: str,
    payload: ModelRegistryActivationClaimIn,
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    if not payload.adapter_id.strip() or not payload.delivery_token.strip():
        raise HTTPException(status_code=422, detail="adapter_id and delivery_token are required")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — registry claim unavailable",
        )
    result = await claim_model_registry_activation_command(
        tenant_id=tenant,
        command_id=activation_command_id,
        adapter_id=payload.adapter_id,
        delivery_token=payload.delivery_token,
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="activation command not found")
    raise HTTPException(
        status_code=409, detail=result.get("reason", "activation command claim conflict")
    )


class ModelRegistryActivationReceiptIn(BaseModel):
    adapter_id: str
    delivery_token: str
    receipt_state: str
    active_artifact_uri: str | None = None
    active_artifact_digest: str | None = None
    registry_version: str | None = None
    failure_reason: str | None = None
    receipt_payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


@app.post("/v1/learning/activation-commands/{activation_command_id}/receipt")
async def record_registry_activation_receipt_boundary(
    activation_command_id: str,
    payload: ModelRegistryActivationReceiptIn,
    x_tenant_id: str | None = Header(default=None),
    x_recorded_by: str | None = Header(default=None),
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    recorded_by = (x_recorded_by or "").strip()
    if not recorded_by:
        raise HTTPException(status_code=400, detail="X-Recorded-By is required")
    if payload.receipt_state not in {"activated", "failed"}:
        raise HTTPException(status_code=422, detail="receipt_state must be activated or failed")
    if not payload.idempotency_key.strip():
        raise HTTPException(status_code=422, detail="idempotency_key is required")
    if payload.receipt_state == "activated":
        if (
            not (payload.active_artifact_uri or "").strip()
            or not (payload.active_artifact_digest or "").strip()
        ):
            raise HTTPException(status_code=422, detail="active artifact proof is required")
        digest = str(payload.active_artifact_digest).lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise HTTPException(status_code=422, detail="active_artifact_digest must be sha256 hex")
    if payload.receipt_state == "failed" and not (payload.failure_reason or "").strip():
        raise HTTPException(status_code=422, detail="failure_reason is required")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — registry receipt unavailable",
        )
    result = await record_model_registry_activation_receipt(
        tenant_id=tenant, command_id=activation_command_id, recorded_by=recorded_by, payload=payload
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="activation command/claim not found")
    raise HTTPException(status_code=409, detail=result.get("reason", "activation receipt conflict"))


class ModelRegistryRollbackIn(BaseModel):
    reason: str
    idempotency_key: str


@app.post("/v1/learning/activation-receipts/{activation_receipt_id}/rollback-command")
async def create_registry_rollback_command_boundary(
    activation_receipt_id: str,
    payload: ModelRegistryRollbackIn,
    x_tenant_id: str | None = Header(default=None),
    x_requested_by: str | None = Header(default=None),
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    requested_by = (x_requested_by or "").strip()
    if not requested_by:
        raise HTTPException(status_code=400, detail="X-Requested-By is required")
    if not payload.reason.strip() or not payload.idempotency_key.strip():
        raise HTTPException(status_code=422, detail="reason and idempotency_key are required")
    if not sor_enabled():
        raise HTTPException(
            status_code=503,
            detail="decision-service is not the system-of-record — rollback command unavailable",
        )
    result = await create_model_registry_rollback_command(
        tenant_id=tenant,
        receipt_id=activation_receipt_id,
        requested_by=requested_by,
        payload=payload,
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="activation receipt not found")
    raise HTTPException(status_code=409, detail=result.get("reason", "rollback command conflict"))


# WX-11.7..WX-11.12 closed-loop completion endpoints -----------------------------
class ModelRegistryRollbackClaimIn(BaseModel):
    adapter_id: str
    delivery_token: str


@app.post("/v1/learning/rollback-commands/{rollback_command_id}/claim")
async def claim_registry_rollback_command_boundary(
    rollback_command_id: str,
    payload: ModelRegistryRollbackClaimIn,
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    if not payload.adapter_id.strip() or not payload.delivery_token.strip():
        raise HTTPException(status_code=422, detail="adapter_id and delivery_token are required")
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    result = await claim_model_registry_rollback_command(
        tenant_id=tenant,
        command_id=rollback_command_id,
        adapter_id=payload.adapter_id,
        delivery_token=payload.delivery_token,
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="rollback command not found")
    raise HTTPException(status_code=409, detail=result.get("reason", "rollback claim conflict"))


class ModelRegistryRollbackReceiptIn(BaseModel):
    adapter_id: str
    delivery_token: str
    receipt_state: str
    active_artifact_uri: str | None = None
    active_artifact_digest: str | None = None
    registry_version: str | None = None
    failure_reason: str | None = None
    receipt_payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


@app.post("/v1/learning/rollback-commands/{rollback_command_id}/receipt")
async def record_registry_rollback_receipt_boundary(
    rollback_command_id: str,
    payload: ModelRegistryRollbackReceiptIn,
    x_tenant_id: str | None = Header(default=None),
    x_recorded_by: str | None = Header(default=None),
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    recorded_by = (x_recorded_by or "").strip()
    if not recorded_by:
        raise HTTPException(status_code=400, detail="X-Recorded-By is required")
    if payload.receipt_state not in {"rolled_back", "rollback_failed"}:
        raise HTTPException(status_code=422, detail="invalid receipt_state")
    if not payload.idempotency_key.strip():
        raise HTTPException(status_code=422, detail="idempotency_key is required")
    if payload.receipt_state == "rolled_back":
        d = (payload.active_artifact_digest or "").lower()
        if (
            not (payload.active_artifact_uri or "").strip()
            or len(d) != 64
            or any(c not in "0123456789abcdef" for c in d)
        ):
            raise HTTPException(status_code=422, detail="valid active artifact proof is required")
    if payload.receipt_state == "rollback_failed" and not (payload.failure_reason or "").strip():
        raise HTTPException(status_code=422, detail="failure_reason is required")
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    result = await record_model_registry_rollback_receipt(
        tenant_id=tenant, command_id=rollback_command_id, recorded_by=recorded_by, payload=payload
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="rollback command/claim not found")
    raise HTTPException(status_code=409, detail=result.get("reason", "rollback receipt conflict"))


@app.get("/v1/learning/models/{model_id}/active-state")
async def active_model_state_boundary(
    model_id: str,
    feature_set_id: str | None = Query(default=None),
    target_environment: str = Query(default="production"),
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    if target_environment not in {"staging", "production"}:
        raise HTTPException(status_code=422, detail="invalid environment")
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    result = await get_active_model_state(
        tenant_id=tenant,
        model_id=model_id,
        feature_set_id=feature_set_id,
        target_environment=target_environment,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="active model state not found")
    return {"tenant_id": tenant, **result}


class PostActivationVerificationIn(BaseModel):
    verification_state: str
    artifact_digest: str
    checks: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float | None = None
    error_rate: float | None = None
    idempotency_key: str


@app.post("/v1/learning/activation-receipts/{activation_receipt_id}/verification")
async def post_activation_verification_boundary(
    activation_receipt_id: str,
    payload: PostActivationVerificationIn,
    x_tenant_id: str | None = Header(default=None),
    x_verified_by: str | None = Header(default=None),
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    actor = (x_verified_by or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="X-Verified-By is required")
    if payload.verification_state not in {
        "verified_healthy",
        "verified_degraded",
        "verification_failed",
    }:
        raise HTTPException(status_code=422, detail="invalid verification_state")
    d = payload.artifact_digest.lower()
    if len(d) != 64 or any(c not in "0123456789abcdef" for c in d):
        raise HTTPException(status_code=422, detail="artifact_digest must be sha256")
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    result = await create_post_activation_verification(
        tenant_id=tenant, receipt_id=activation_receipt_id, verified_by=actor, payload=payload
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="activated receipt not found")
    raise HTTPException(status_code=409, detail=result.get("reason", "verification conflict"))


class RolloutPlanIn(BaseModel):
    mode: str
    traffic_percent: float
    policy: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


@app.post("/v1/learning/activation-receipts/{activation_receipt_id}/rollout-plan")
async def rollout_plan_boundary(
    activation_receipt_id: str,
    payload: RolloutPlanIn,
    x_tenant_id: str | None = Header(default=None),
    x_requested_by: str | None = Header(default=None),
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    actor = (x_requested_by or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="X-Requested-By is required")
    if payload.mode not in {"shadow", "canary", "full"} or not 0 <= payload.traffic_percent <= 100:
        raise HTTPException(status_code=422, detail="invalid rollout plan")
    if payload.mode == "shadow" and payload.traffic_percent != 0:
        raise HTTPException(status_code=422, detail="shadow traffic_percent must be 0")
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    result = await create_rollout_plan(
        tenant_id=tenant, receipt_id=activation_receipt_id, requested_by=actor, payload=payload
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    raise HTTPException(status_code=409, detail=result.get("reason", "rollout conflict"))


class MonitoringSnapshotIn(BaseModel):
    model_id: str
    feature_set_id: str | None = None
    target_environment: str
    window_start: datetime
    window_end: datetime
    sample_count: int
    metrics: dict[str, Any] = Field(default_factory=dict)
    drift_state: str
    idempotency_key: str


@app.post("/v1/learning/monitoring-snapshots")
async def monitoring_snapshot_boundary(
    payload: MonitoringSnapshotIn,
    x_tenant_id: str | None = Header(default=None),
    x_captured_by: str | None = Header(default=None),
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    actor = (x_captured_by or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="X-Captured-By is required")
    if (
        payload.drift_state not in {"stable", "warning", "critical"}
        or payload.sample_count < 0
        or payload.window_end <= payload.window_start
    ):
        raise HTTPException(status_code=422, detail="invalid monitoring snapshot")
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    result = await record_monitoring_snapshot(tenant_id=tenant, captured_by=actor, payload=payload)
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    raise HTTPException(status_code=409, detail=result.get("reason", "monitoring conflict"))


class RetrainingRequestIn(BaseModel):
    model_id: str
    feature_set_id: str | None = None
    target_environment: str = "production"
    source_monitoring_snapshot_id: str | None = None
    dataset_fingerprint: str
    training_manifest: dict[str, Any]
    code_version: str
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


@app.post("/v1/learning/retraining-requests")
async def retraining_request_boundary(
    payload: RetrainingRequestIn,
    x_tenant_id: str | None = Header(default=None),
    x_requested_by: str | None = Header(default=None),
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    actor = (x_requested_by or "").strip()
    d = payload.dataset_fingerprint.lower()
    if not actor:
        raise HTTPException(status_code=400, detail="X-Requested-By is required")
    if len(d) != 64 or any(c not in "0123456789abcdef" for c in d):
        raise HTTPException(status_code=422, detail="dataset_fingerprint must be sha256")
    if payload.target_environment not in {"staging", "production"}:
        raise HTTPException(status_code=422, detail="invalid target_environment")
    if not payload.code_version.strip() or not payload.training_manifest:
        raise HTTPException(
            status_code=422, detail="immutable training manifest and code_version are required"
        )
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    result = await create_retraining_request(tenant_id=tenant, requested_by=actor, payload=payload)
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    raise HTTPException(status_code=409, detail=result.get("reason", "retraining conflict"))


# --- WX-12.1 runtime integration: work feed + rollout/dispatch acknowledgement receipts -------


@app.get("/v1/learning/runtime-work")
async def runtime_work_feed(
    worker_id: str = Query(default=""),
    limit: int = Query(default=20),
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Authoritative pending-work feed; side-effecting work rides durable leases (migration 016)."""
    tenant = _tenant(x_tenant_id)
    wid = (worker_id or "").strip()
    if not wid:
        raise HTTPException(status_code=400, detail="worker_id is required")
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    # WX-12 multitenancy: once a worker is registered, it may only pull work for its
    # operator-authorized tenants — the header stops being a free pick (migration 024).
    if not await worker_tenant_authorized(worker_id=wid, tenant_id=tenant):
        raise HTTPException(
            status_code=403,
            detail={"code": "worker_tenant_unauthorized", "worker_id": wid},
        )
    return await list_runtime_work(tenant_id=tenant, worker_id=wid, limit=limit)


class RuntimeWorkerTenantIn(BaseModel):
    tenant_id: str
    enabled: bool = True
    idempotency_key: str


@app.post("/v1/learning/runtime-workers/{worker_id}/tenants")
async def register_worker_tenant(
    worker_id: str,
    payload: RuntimeWorkerTenantIn,
    x_registered_by: str | None = Header(default=None),
) -> dict[str, Any]:
    """Operator registration of a worker→tenant authorization (idempotent upsert)."""
    actor = (x_registered_by or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="X-Registered-By is required")
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    try:
        UUID(payload.tenant_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="tenant_id must be a uuid") from None
    result = await register_runtime_worker_tenant(
        worker_id=worker_id.strip(), created_by=actor, payload=payload
    )
    if result.get("status") == "conflict":
        raise HTTPException(status_code=409, detail=result.get("reason"))
    return result


@app.get("/v1/learning/runtime-workers/{worker_id}/tenants")
async def worker_tenants(worker_id: str) -> dict[str, Any]:
    """Server-side tenant discovery for a worker (the adapter enumerates its partition
    from here instead of free-picking tenants; empty when unregistered)."""
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    return await list_worker_tenants(worker_id=worker_id.strip())


class RolloutReceiptIn(BaseModel):
    receipt_state: str
    controller_id: str
    observed_traffic_percent: float | None = None
    candidate_artifact_digest: str | None = None
    routing_version: str | None = None
    failure_reason: str | None = None
    receipt_payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


@app.post("/v1/learning/rollout-plans/{rollout_plan_id}/receipt")
async def rollout_receipt_boundary(
    rollout_plan_id: str,
    payload: RolloutReceiptIn,
    x_tenant_id: str | None = Header(default=None),
    x_recorded_by: str | None = Header(default=None),
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    actor = (x_recorded_by or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="X-Recorded-By is required")
    if payload.receipt_state not in {"applied", "rollout_failed"}:
        raise HTTPException(
            status_code=422, detail="receipt_state must be applied or rollout_failed"
        )
    if not payload.idempotency_key.strip():
        raise HTTPException(status_code=422, detail="idempotency_key is required")
    if payload.receipt_state == "rollout_failed" and not (payload.failure_reason or "").strip():
        raise HTTPException(status_code=422, detail="failure_reason is required")
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    result = await record_rollout_receipt(
        tenant_id=tenant, recorded_by=actor, rollout_plan_id=rollout_plan_id, payload=payload
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result.get("reason"))
    raise HTTPException(status_code=409, detail=result.get("reason", "rollout receipt conflict"))


class RetrainingDispatchReceiptIn(BaseModel):
    dispatch_state: str
    dispatcher_id: str
    job_id: str | None = None
    backend: str | None = None
    failure_reason: str | None = None
    receipt_payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


@app.post("/v1/learning/retraining-requests/{retraining_request_id}/dispatch-receipt")
async def retraining_dispatch_receipt_boundary(
    retraining_request_id: str,
    payload: RetrainingDispatchReceiptIn,
    x_tenant_id: str | None = Header(default=None),
    x_recorded_by: str | None = Header(default=None),
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    actor = (x_recorded_by or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="X-Recorded-By is required")
    if payload.dispatch_state not in {"dispatched", "dispatch_failed"}:
        raise HTTPException(
            status_code=422, detail="dispatch_state must be dispatched or dispatch_failed"
        )
    if not payload.idempotency_key.strip():
        raise HTTPException(status_code=422, detail="idempotency_key is required")
    if payload.dispatch_state == "dispatched" and not (payload.job_id or "").strip():
        raise HTTPException(status_code=422, detail="job_id is required for a dispatched receipt")
    if payload.dispatch_state == "dispatch_failed" and not (payload.failure_reason or "").strip():
        raise HTTPException(status_code=422, detail="failure_reason is required")
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    result = await record_retraining_dispatch_receipt(
        tenant_id=tenant,
        recorded_by=actor,
        retraining_request_id=retraining_request_id,
        payload=payload,
    )
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result.get("reason"))
    raise HTTPException(status_code=409, detail=result.get("reason", "dispatch receipt conflict"))


# --- WX-12.3 durable runtime schedules + reconcile evidence -----------------------------------


class RuntimeScheduleIn(BaseModel):
    kind: str
    model_id: str
    feature_set_id: str | None = None
    target_environment: str
    period_seconds: int
    idempotency_key: str


@app.post("/v1/learning/runtime-schedules")
async def runtime_schedule_boundary(
    payload: RuntimeScheduleIn,
    x_tenant_id: str | None = Header(default=None),
    x_requested_by: str | None = Header(default=None),
) -> dict[str, Any]:
    """Register durable schedule CONFIG for monitoring windows / active-state reconciliation.

    No schedule rows => the runtime-work feed emits nothing scheduled (zero behavior change) —
    creating a row IS the enablement flag. Progression is derived from append-only evidence
    (monitoring snapshots / reconcile evidence), never from mutable last-run state.
    """
    tenant = _tenant(x_tenant_id)
    actor = (x_requested_by or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="X-Requested-By is required")
    if payload.kind not in {"monitoring_window", "active_state_reconcile"}:
        raise HTTPException(
            status_code=422, detail="kind must be monitoring_window or active_state_reconcile"
        )
    if payload.target_environment not in {"staging", "production"}:
        raise HTTPException(status_code=422, detail="invalid environment")
    if payload.period_seconds < 60:
        raise HTTPException(status_code=422, detail="period_seconds must be >= 60")
    if not payload.idempotency_key.strip() or not payload.model_id.strip():
        raise HTTPException(status_code=422, detail="model_id and idempotency_key are required")
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    result = await create_runtime_schedule(tenant_id=tenant, created_by=actor, payload=payload)
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    raise HTTPException(status_code=409, detail=result.get("reason", "schedule conflict"))


class ReconcileEvidenceIn(BaseModel):
    schedule_id: str | None = None
    model_id: str
    feature_set_id: str | None = None
    target_environment: str
    expected_artifact_digest: str
    observed_artifact_digest: str
    drift_detected: bool
    registry_version: str | None = None
    evidence_payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


@app.post("/v1/learning/reconcile-evidence")
async def reconcile_evidence_boundary(
    payload: ReconcileEvidenceIn,
    x_tenant_id: str | None = Header(default=None),
    x_recorded_by: str | None = Header(default=None),
) -> dict[str, Any]:
    """Append-only projection-vs-registry comparison evidence (drift is auditable, not log-only)."""
    tenant = _tenant(x_tenant_id)
    actor = (x_recorded_by or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="X-Recorded-By is required")
    for d in (payload.expected_artifact_digest, payload.observed_artifact_digest):
        h = d.lower()
        if len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
            raise HTTPException(status_code=422, detail="artifact digests must be sha256 hex")
    if payload.target_environment not in {"staging", "production"}:
        raise HTTPException(status_code=422, detail="invalid environment")
    if not payload.idempotency_key.strip():
        raise HTTPException(status_code=422, detail="idempotency_key is required")
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    result = await record_reconcile_evidence(tenant_id=tenant, recorded_by=actor, payload=payload)
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    raise HTTPException(status_code=409, detail=result.get("reason", "reconcile conflict"))


# --- AC-1 agronomic context composer (skeleton): immutable snapshots + PIT enforcement --------


@app.post("/v1/context-snapshots")
async def compose_context_snapshot(
    payload: ContextComposeIn,
    x_tenant_id: str | None = Header(default=None),
    x_requested_by: str | None = Header(default=None),
) -> dict[str, Any]:
    """Compose the three immutable context contracts from source-attributed evidence.

    Fail-closed: any point-in-time violation (available_at after the decision cutoff), missing
    context group, or inconsistent quality state rejects the whole composition with TYPED reasons
    — no value is ever silently synthesized. Content hashes make replay deterministic and enable
    snapshot reuse.
    """
    tenant = _tenant(x_tenant_id)
    actor = (x_requested_by or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="X-Requested-By is required")
    if not payload.idempotency_key.strip():
        raise HTTPException(status_code=422, detail="idempotency_key is required")
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    result = await compose_agronomic_context(tenant_id=tenant, created_by=actor, payload=payload)
    if result.get("status") == "ok":
        return {"accepted": True, "tenant_id": tenant, **result}
    if result.get("status") == "rejected":
        raise HTTPException(
            status_code=422,
            detail={"reason": result.get("reason"), "violations": result.get("violations", [])},
        )
    raise HTTPException(status_code=409, detail=result.get("reason", "context conflict"))


@app.get("/v1/context-snapshots/{snapshot_id}")
async def read_context_snapshot(
    snapshot_id: str,
    x_tenant_id: str | None = Header(default=None),
) -> dict[str, Any]:
    tenant = _tenant(x_tenant_id)
    if not sor_enabled():
        raise HTTPException(status_code=503, detail="decision-service is not the system-of-record")
    result = await get_context_snapshot(tenant_id=tenant, snapshot_id=snapshot_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="context snapshot not found")
    return {"tenant_id": tenant, **result}
