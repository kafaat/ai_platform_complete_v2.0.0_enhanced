"""api/routers/decision_review.py — WX-10.7 reviewer/policy action on a decision candidate.

# DECISION-PATH: reviewer/policy transition of a pending_approval candidate to a terminal
# approved|rejected Decision Record. The AUTHORITATIVE state machine, append-only audit, and
# transaction are OWNED BY decision-service — this platform route is a thin, authenticated BFF
# proxy: it enforces *who* may review (role permission) and forwards to decision-service, then
# fails closed unless the service proves an authoritative transition. It never mutates the
# decision itself, and never dispatches / creates tasks / executes equipment.

Ownership split (continuation of WX-10.6): Crop Intelligence interprets; decision-service owns
the decision, its approval, and the review audit. Reopen/correction is a future increment with
its own audit contract — this route only performs the single terminal transition.
"""

from __future__ import annotations

from core.authorization import Permission
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.decision_service_client import list_review_queue as ds_list_review_queue
from api.decision_service_client import review_decision as ds_review_decision
from api.main import UserSchema, require_permission

router = APIRouter()

_ENGINE_DOWN_CODES = {502, 503, 504}
_TERMINAL_STATES = {"approved", "rejected"}


class DecisionReviewRequest(BaseModel):
    """طلب مراجعة مرشّح قرار (approve/reject) بضوابط التزامن والنَّسَب."""

    action: str  # "approve" | "reject"
    reason: str = ""
    expected_state: str = "pending_approval"
    candidate_lineage_id: str
    idempotency_key: str
    policy_version: str | None = None


@router.get("/api/v1/decisions/review-queue")
async def get_decision_review_queue(
    limit: int = 100,
    user: UserSchema = Depends(require_permission(Permission.DECISION_APPROVE)),
):
    """WX-10.8 — authenticated BFF pass-through for the authoritative review queue."""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 200")
    try:
        result = await ds_list_review_queue(
            tenant_id=str(user.tenant_id) if user.tenant_id else None, limit=limit
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503, detail="decision-service unavailable — review queue not read"
            ) from exc
        raise
    if result.get("authoritative") is not True or result.get("persisted") is not True:
        raise HTTPException(status_code=503, detail="non-authoritative review queue rejected")
    items = result.get("items")
    if not isinstance(items, list) or result.get("count") != len(items):
        raise HTTPException(status_code=503, detail="invalid authoritative review queue contract")
    return result


@router.post("/api/v1/decisions/{decision_id}/review")
async def review_decision_candidate(
    decision_id: str,
    req: DecisionReviewRequest,
    user: UserSchema = Depends(require_permission(Permission.DECISION_APPROVE)),
):
    """WX-10.7 — مراجعة مُصرَّح بها لمرشّح ``pending_approval`` → ``approved|rejected``.

    الملكيّة: decision-service يملك الانتقال الآمِر (state machine + audit + transaction). هذه
    النقطة تفرض *مَن* يراجع (``DECISION_APPROVE``) وتُمرّر فقط؛ tenant من الـJWT، ``reviewed_by``
    من المستخدم. **fail-closed:** لا نجاح إلّا إذا أثبت ردّ الخدمة الانتقال الآمِر (authoritative
    ∧ persisted ∧ decision_id مطابق ∧ previous_state=pending_approval ∧ state∈{approved,rejected}
    ∧ review_id/reviewed_by/reviewed_at غير فارغة ∧ candidate_lineage_id مطابق). mirror/SoR-off ⇒
    ردّ غير آمِر ⇒ 503. الخدمة ساقطة ⇒ 503. لا تنفيذ (dispatch/task/معدّات)."""
    payload = {
        "action": req.action,
        "reason": req.reason,
        "expected_state": req.expected_state,
        "candidate_lineage_id": req.candidate_lineage_id,
        "idempotency_key": req.idempotency_key,
        "policy_version": req.policy_version,
    }
    try:
        result = await ds_review_decision(
            decision_id,
            payload,
            tenant_id=str(user.tenant_id) if user.tenant_id else None,
            reviewed_by=user.user_id,
        )
    except HTTPException as exc:
        # decision-service unavailable → fail closed as 503; 404/409/422 propagate verbatim.
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503, detail="decision-service unavailable — review not applied"
            ) from exc
        raise

    # fail-closed proof — a review is successful ONLY when the service proves the authoritative
    # transition of the same record with a real audit row. The platform never synthesizes this.
    proven = (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("decision_id") == decision_id
        and result.get("previous_state") == "pending_approval"
        and result.get("state") in _TERMINAL_STATES
        and bool(result.get("review_id"))
        and bool(result.get("reviewed_by"))
        and bool(result.get("reviewed_at"))
        and result.get("candidate_lineage_id") == req.candidate_lineage_id
    )
    if not proven:
        raise HTTPException(
            status_code=503,
            detail="decision-service did not confirm an authoritative review — fail-closed",
        )
    return {
        "decision_id": decision_id,
        "state": result["state"],
        "previous_state": result["previous_state"],
        "review_id": result["review_id"],
        "reviewed_by": result["reviewed_by"],
        "reviewed_at": result["reviewed_at"],
        "candidate_lineage_id": result["candidate_lineage_id"],
        "replay": bool(result.get("replay", False)),
    }


class ExecutionPlanRequest(BaseModel):
    review_id: str
    candidate_lineage_id: str
    operation_type: str
    planned_start: str | None = None
    planned_end: str | None = None
    target_zone_ids: list[str] = Field(default_factory=list)
    required_resources: list[dict] = Field(default_factory=list)
    constraints: dict = Field(default_factory=dict)
    safety_conditions: dict = Field(default_factory=dict)
    weather_window_reference: dict | None = None
    idempotency_key: str


@router.post("/api/v1/decisions/{decision_id}/execution-plan")
async def create_decision_execution_plan(
    decision_id: str,
    req: ExecutionPlanRequest,
    user: UserSchema = Depends(require_permission(Permission.DECISION_APPROVE)),
):
    """WX-10.9 thin BFF. Creates a planned record only; no dispatch/task/equipment effects."""
    from api.decision_service_client import create_execution_plan as ds_create_execution_plan

    try:
        result = await ds_create_execution_plan(
            decision_id,
            req.model_dump(),
            tenant_id=str(user.tenant_id) if user.tenant_id else None,
            created_by=user.user_id,
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503, detail="decision-service execution planning unavailable"
            ) from exc
        raise
    proven = (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("decision_id") == decision_id
        and result.get("review_id") == req.review_id
        and result.get("candidate_lineage_id") == req.candidate_lineage_id
        and result.get("plan_state") == "planned"
        and bool(result.get("execution_plan_id"))
        and bool(result.get("created_by"))
        and bool(result.get("created_at"))
    )
    if not proven:
        raise HTTPException(
            status_code=503, detail="decision-service did not prove an authoritative execution plan"
        )
    return {
        "execution_plan_id": result["execution_plan_id"],
        "decision_id": decision_id,
        "review_id": result["review_id"],
        "candidate_lineage_id": result["candidate_lineage_id"],
        "state": "planned",
        "replay": bool(result.get("replay", False)),
        "created_at": result["created_at"],
    }


class DispatchAuthorizationRequest(BaseModel):
    decision_id: str
    review_id: str
    candidate_lineage_id: str
    expected_plan_state: str = "planned"
    policy_version: str
    weather_snapshot_id: str
    resource_snapshot_id: str
    authorization_reason: str | None = None
    idempotency_key: str


@router.post("/api/v1/execution-plans/{execution_plan_id}/authorize-dispatch")
async def authorize_execution_plan_dispatch(
    execution_plan_id: str,
    req: DispatchAuthorizationRequest,
    user: UserSchema = Depends(require_permission(Permission.DECISION_DISPATCH_AUTHORIZE)),
):
    """WX-10.10 thin BFF. Persists authorization only; never dispatches or creates tasks."""
    from api.decision_service_client import authorize_dispatch as ds_authorize_dispatch

    try:
        result = await ds_authorize_dispatch(
            execution_plan_id,
            req.model_dump(),
            tenant_id=str(user.tenant_id) if user.tenant_id else None,
            authorized_by=user.user_id,
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503, detail="decision-service dispatch authorization unavailable"
            ) from exc
        raise
    proven = (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("execution_plan_id") == execution_plan_id
        and result.get("decision_id") == req.decision_id
        and result.get("review_id") == req.review_id
        and result.get("candidate_lineage_id") == req.candidate_lineage_id
        and result.get("authorization_state") == "authorized"
        and result.get("policy_version") == req.policy_version
        and result.get("weather_snapshot_id") == req.weather_snapshot_id
        and result.get("resource_snapshot_id") == req.resource_snapshot_id
        and bool(result.get("dispatch_authorization_id"))
        and bool(result.get("authorized_by"))
        and bool(result.get("authorized_at"))
    )
    if not proven:
        raise HTTPException(
            status_code=503,
            detail="decision-service did not prove an authoritative dispatch authorization",
        )
    return {
        "dispatch_authorization_id": result["dispatch_authorization_id"],
        "execution_plan_id": execution_plan_id,
        "decision_id": result["decision_id"],
        "review_id": result["review_id"],
        "candidate_lineage_id": result["candidate_lineage_id"],
        "state": "authorized",
        "replay": bool(result.get("replay", False)),
        "authorized_at": result["authorized_at"],
    }


class ExecutionRequest(BaseModel):
    dispatch_authorization_id: str
    execution_plan_id: str
    decision_id: str
    target_type: str
    target_id: str
    operation_type: str
    command_payload: dict = {}
    idempotency_key: str


@router.post("/api/v1/dispatch-authorizations/{dispatch_authorization_id}/execute")
async def create_authorized_execution_request(
    dispatch_authorization_id: str,
    req: ExecutionRequest,
    user: UserSchema = Depends(require_permission(Permission.DECISION_EXECUTE)),
):
    """WX-10.11a thin BFF; persists one queued task/equipment execution request."""
    from api.decision_service_client import create_execution_request as ds_create_execution_request

    try:
        result = await ds_create_execution_request(
            dispatch_authorization_id,
            req.model_dump(),
            tenant_id=str(user.tenant_id) if user.tenant_id else None,
            requested_by=user.user_id,
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503, detail="decision-service execution unavailable"
            ) from exc
        raise
    proven = (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("dispatch_authorization_id") == dispatch_authorization_id
        and result.get("execution_plan_id") == req.execution_plan_id
        and result.get("decision_id") == req.decision_id
        and result.get("target_type") == req.target_type
        and result.get("target_id") == req.target_id
        and result.get("operation_type") == req.operation_type
        and result.get("execution_state") == "queued"
        and bool(result.get("execution_request_id"))
        and bool(result.get("requested_by"))
        and bool(result.get("requested_at"))
    )
    if not proven:
        raise HTTPException(
            status_code=503,
            detail="decision-service did not prove an authoritative execution request",
        )
    return {
        "execution_request_id": result["execution_request_id"],
        "dispatch_authorization_id": dispatch_authorization_id,
        "execution_plan_id": result["execution_plan_id"],
        "decision_id": result["decision_id"],
        "target_type": result["target_type"],
        "target_id": result["target_id"],
        "operation_type": result["operation_type"],
        "state": "queued",
        "replay": bool(result.get("replay", False)),
        "requested_at": result["requested_at"],
    }


class ExecutionOutcomeVerificationRequest(BaseModel):
    execution_plan_id: str
    dispatch_authorization_id: str
    decision_id: str
    receipt_id: str
    verification_state: str
    evidence_snapshot_id: str
    actual: dict = {}
    metrics: dict = {}
    idempotency_key: str


@router.post("/api/v1/execution-requests/{execution_request_id}/verify-outcome")
async def verify_execution_outcome_boundary(
    execution_request_id: str,
    req: ExecutionOutcomeVerificationRequest,
    user: UserSchema = Depends(require_permission(Permission.DECISION_EXECUTE)),
):
    """WX-10.12 thin BFF; decision-service persists the immutable canonical outcome."""
    from api.decision_service_client import verify_execution_outcome as ds_verify_execution_outcome

    try:
        result = await ds_verify_execution_outcome(
            execution_request_id,
            req.model_dump(),
            tenant_id=str(user.tenant_id) if user.tenant_id else None,
            verified_by=user.user_id,
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503, detail="decision-service outcome verification unavailable"
            ) from exc
        raise
    proven = (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("execution_request_id") == execution_request_id
        and result.get("execution_plan_id") == req.execution_plan_id
        and result.get("dispatch_authorization_id") == req.dispatch_authorization_id
        and result.get("decision_id") == req.decision_id
        and result.get("receipt_id") == req.receipt_id
        and result.get("verification_state") == req.verification_state
        and result.get("evidence_snapshot_id") == req.evidence_snapshot_id
        and bool(result.get("outcome_id"))
        and bool(result.get("verified_by"))
        and bool(result.get("verified_at"))
    )
    if not proven:
        raise HTTPException(
            status_code=503, detail="decision-service did not prove an authoritative outcome"
        )
    return {
        "outcome_id": result["outcome_id"],
        "execution_request_id": execution_request_id,
        "decision_id": result["decision_id"],
        "state": result["verification_state"],
        "success": result["success"],
        "evidence_snapshot_id": result["evidence_snapshot_id"],
        "replay": bool(result.get("replay", False)),
        "verified_at": result["verified_at"],
    }
