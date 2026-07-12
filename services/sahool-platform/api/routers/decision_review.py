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


@router.get("/api/v1/decisions/{decision_id}/agronomic-evidence")
async def get_decision_agronomic_evidence_boundary(
    decision_id: str,
    user: UserSchema = Depends(require_permission(Permission.DECISION_APPROVE)),
):
    """Phase E — الدليل الزراعيّ الكامل خلف قرار واحد (سياق/تاريخ/manifest/نباتيّ).

    قراءة آمِرة فقط: decision-service يملك الحقيقة؛ mirror/SoR-off ⇒ 503 هناك ويُمرَّر
    هنا (fail-closed — لا "لا يوجد دليل" زائف). المراجِع يرى الدليل قبل approve/reject،
    لذلك الصلاحيّة نفسها ``DECISION_APPROVE``. لا تحويل ولا تخليق للحمولة."""
    from api.decision_service_client import (
        get_decision_agronomic_evidence as ds_get_decision_evidence,
    )

    try:
        result = await ds_get_decision_evidence(
            decision_id, tenant_id=str(user.tenant_id) if user.tenant_id else None
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503, detail="decision-service unavailable — evidence not read"
            ) from exc
        raise
    proven = (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("read_only") is True
        and result.get("decision_id") == decision_id
        and isinstance(result.get("decision"), dict)
    )
    if not proven:
        raise HTTPException(status_code=503, detail="non-authoritative evidence rejected")
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


class LearningAttributionRequest(BaseModel):
    model_id: str
    feature_set_id: str | None = None
    attribution_method: str = "verified_outcome"
    label: str
    weight: float = 1.0
    evidence_snapshot_id: str
    idempotency_key: str
    metadata: dict = {}


@router.post("/api/v1/outcomes/{outcome_id}/learning-attribution")
async def create_learning_attribution_boundary(
    outcome_id: str,
    req: LearningAttributionRequest,
    user: UserSchema = Depends(require_permission(Permission.DECISION_LEARNING_ATTRIBUTE)),
):
    """WX-10.13 thin BFF; attribution only, never a model mutation."""
    from api.decision_service_client import create_learning_attribution as ds_create_attribution

    try:
        result = await ds_create_attribution(
            outcome_id,
            req.model_dump(),
            tenant_id=str(user.tenant_id) if user.tenant_id else None,
            attributed_by=user.user_id,
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503, detail="decision-service learning attribution unavailable"
            ) from exc
        raise
    proven = (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("outcome_id") == outcome_id
        and result.get("model_id") == req.model_id
        and result.get("feature_set_id") == req.feature_set_id
        and result.get("attribution_method") == req.attribution_method
        and result.get("label") == req.label
        and result.get("evidence_snapshot_id") == req.evidence_snapshot_id
        and result.get("learning_state") == "attributed"
        and bool(result.get("learning_attribution_id"))
        and bool(result.get("attributed_by"))
        and bool(result.get("attributed_at"))
    )
    if not proven:
        raise HTTPException(
            status_code=503,
            detail="decision-service did not prove an authoritative learning attribution",
        )
    return {
        "learning_attribution_id": result["learning_attribution_id"],
        "outcome_id": outcome_id,
        "decision_id": result["decision_id"],
        "execution_request_id": result["execution_request_id"],
        "model_id": result["model_id"],
        "feature_set_id": result["feature_set_id"],
        "label": result["label"],
        "weight": result["weight"],
        "learning_state": "attributed",
        "replay": bool(result.get("replay", False)),
        "attributed_at": result["attributed_at"],
    }


@router.get("/api/v1/learning/calibration-dataset")
async def read_calibration_dataset_boundary(
    model_id: str,
    feature_set_id: str | None = None,
    limit: int = 500,
    user: UserSchema = Depends(require_permission(Permission.DECISION_LEARNING_ATTRIBUTE)),
):
    """WX-11.1 thin BFF; returns immutable calibration evidence only."""
    from api.decision_service_client import get_calibration_dataset

    try:
        result = await get_calibration_dataset(
            model_id=model_id,
            feature_set_id=feature_set_id,
            limit=limit,
            tenant_id=str(user.tenant_id) if user.tenant_id else None,
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503, detail="decision-service calibration dataset unavailable"
            ) from exc
        raise
    proven = (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("read_only") is True
        and result.get("model_id") == model_id
        and result.get("feature_set_id") == feature_set_id
        and isinstance(result.get("items"), list)
    )
    if not proven:
        raise HTTPException(
            status_code=503,
            detail="decision-service did not prove an authoritative calibration dataset",
        )
    return result


class ModelEvaluationRunRequest(BaseModel):
    model_id: str
    feature_set_id: str | None = None
    dataset_fingerprint: str
    dataset_count: int = Field(gt=0)
    evaluator_version: str
    baseline_metrics: dict
    candidate_metrics: dict
    candidate_artifact_uri: str
    candidate_artifact_digest: str
    artifact_format: str
    idempotency_key: str
    metadata: dict = Field(default_factory=dict)


@router.post("/api/v1/learning/evaluation-runs")
async def register_model_evaluation_boundary(
    req: ModelEvaluationRunRequest,
    user: UserSchema = Depends(require_permission(Permission.DECISION_LEARNING_ATTRIBUTE)),
):
    """WX-11.2 BFF: register evaluated candidate metadata; no training or promotion."""
    from api.decision_service_client import create_model_evaluation_run

    try:
        result = await create_model_evaluation_run(
            req.model_dump(),
            tenant_id=str(user.tenant_id) if user.tenant_id else None,
            evaluated_by=user.user_id,
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503, detail="decision-service evaluation registry unavailable"
            ) from exc
        raise
    proven = (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("model_id") == req.model_id
        and result.get("feature_set_id") == req.feature_set_id
        and result.get("dataset_fingerprint") == req.dataset_fingerprint
        and result.get("dataset_count") == req.dataset_count
        and result.get("candidate_artifact_digest") == req.candidate_artifact_digest.lower()
        and result.get("evaluation_state") == "evaluated"
        and bool(result.get("evaluation_run_id"))
        and bool(result.get("evaluated_by"))
    )
    if not proven:
        raise HTTPException(
            status_code=503, detail="decision-service did not prove an authoritative evaluation run"
        )
    return result


class ModelPromotionDecisionRequest(BaseModel):
    evaluation_run_id: str
    policy_version: str
    primary_metric: str
    min_improvement: float = 0.0
    lower_is_better: bool = False
    max_regression: float = Field(default=0.0, ge=0.0)
    guardrail_metrics: list[str] = Field(default_factory=list)
    idempotency_key: str
    metadata: dict = Field(default_factory=dict)


@router.post("/api/v1/learning/promotion-decisions")
async def register_model_promotion_decision_boundary(
    req: ModelPromotionDecisionRequest,
    user: UserSchema = Depends(require_permission(Permission.DECISION_LEARNING_ATTRIBUTE)),
):
    """WX-11.3 BFF: record policy eligibility/rejection; never activate a model."""
    from api.decision_service_client import create_model_promotion_decision

    try:
        result = await create_model_promotion_decision(
            req.model_dump(),
            tenant_id=str(user.tenant_id) if user.tenant_id else None,
            decided_by=user.user_id,
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503, detail="decision-service promotion decision unavailable"
            ) from exc
        raise
    proven = (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("evaluation_run_id") == req.evaluation_run_id
        and result.get("policy_version") == req.policy_version
        and result.get("decision_state") in {"promotion_eligible", "promotion_rejected"}
        and bool(result.get("promotion_decision_id"))
        and bool(result.get("candidate_artifact_digest"))
        and bool(result.get("decided_by"))
    )
    if not proven:
        raise HTTPException(
            status_code=503,
            detail="decision-service did not prove an authoritative promotion decision",
        )
    return result


class ModelActivationRequest(BaseModel):
    promotion_decision_id: str
    target_environment: str
    idempotency_key: str
    metadata: dict = Field(default_factory=dict)


@router.post("/api/v1/learning/activation-requests")
async def register_model_activation_request_boundary(
    req: ModelActivationRequest,
    user: UserSchema = Depends(require_permission(Permission.DECISION_MODEL_ACTIVATION_REQUEST)),
):
    """WX-11.4 BFF: create a pending activation request; never mutate registry state."""
    from api.decision_service_client import create_model_activation_request

    try:
        result = await create_model_activation_request(
            req.model_dump(),
            tenant_id=str(user.tenant_id) if user.tenant_id else None,
            requested_by=user.user_id,
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503, detail="decision-service activation request unavailable"
            ) from exc
        raise
    proven = (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("promotion_decision_id") == req.promotion_decision_id
        and result.get("target_environment") == req.target_environment
        and result.get("requested_state") == "pending_activation_approval"
        and bool(result.get("activation_request_id"))
        and bool(result.get("candidate_artifact_digest"))
        and bool(result.get("requested_by"))
    )
    if not proven:
        raise HTTPException(
            status_code=503,
            detail="decision-service did not prove an authoritative activation request",
        )
    return result


class ModelActivationReview(BaseModel):
    review_decision: str
    review_reason: str | None = None
    registry_alias: str | None = None
    previous_artifact_uri: str | None = None
    previous_artifact_digest: str | None = None
    idempotency_key: str
    metadata: dict = Field(default_factory=dict)


@router.post("/api/v1/learning/activation-requests/{activation_request_id}/review")
async def review_model_activation_request_boundary(
    activation_request_id: str,
    req: ModelActivationReview,
    user: UserSchema = Depends(require_permission(Permission.DECISION_MODEL_ACTIVATION_APPROVE)),
):
    """WX-11.5 BFF: governed review and queued registry command; never mutates an alias directly."""
    from api.decision_service_client import review_model_activation_request

    try:
        result = await review_model_activation_request(
            activation_request_id,
            req.model_dump(),
            tenant_id=str(user.tenant_id) if user.tenant_id else None,
            reviewed_by=user.user_id,
        )
    except HTTPException as exc:
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503, detail="decision-service activation review unavailable"
            ) from exc
        raise
    proven = (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("activation_request_id") == activation_request_id
        and result.get("review_decision") == req.review_decision
        and bool(result.get("activation_review_id"))
        and bool(result.get("reviewed_by"))
    )
    if req.review_decision == "approved":
        command = result.get("activation_command") or {}
        proven = (
            proven
            and command.get("command_state") == "queued"
            and command.get("registry_alias") == req.registry_alias
            and command.get("previous_artifact_digest") == str(req.previous_artifact_digest).lower()
            and bool(command.get("activation_command_id"))
        )
    else:
        proven = proven and result.get("activation_command") is None
    if not proven:
        raise HTTPException(
            status_code=503,
            detail="decision-service did not prove an authoritative activation review",
        )
    return result


class RegistryActivationClaim(BaseModel):
    adapter_id: str
    delivery_token: str


@router.post("/api/v1/learning/activation-commands/{activation_command_id}/claim")
async def claim_registry_activation_command_bff(
    activation_command_id: str,
    req: RegistryActivationClaim,
    user: UserSchema = Depends(require_permission(Permission.DECISION_MODEL_REGISTRY_EXECUTE)),
):
    from api.decision_service_client import claim_model_registry_activation_command

    result = await claim_model_registry_activation_command(
        activation_command_id,
        req.model_dump(),
        tenant_id=str(user.tenant_id) if user.tenant_id else None,
    )
    if not (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("activation_command_id") == activation_command_id
        and result.get("claim_state") == "claimed"
    ):
        raise HTTPException(
            status_code=503, detail="decision-service did not prove an authoritative registry claim"
        )
    return result


class RegistryActivationReceipt(BaseModel):
    adapter_id: str
    delivery_token: str
    receipt_state: str
    active_artifact_uri: str | None = None
    active_artifact_digest: str | None = None
    registry_version: str | None = None
    failure_reason: str | None = None
    receipt_payload: dict = Field(default_factory=dict)
    idempotency_key: str


@router.post("/api/v1/learning/activation-commands/{activation_command_id}/receipt")
async def record_registry_activation_receipt_bff(
    activation_command_id: str,
    req: RegistryActivationReceipt,
    user: UserSchema = Depends(require_permission(Permission.DECISION_MODEL_REGISTRY_EXECUTE)),
):
    from api.decision_service_client import record_model_registry_activation_receipt

    result = await record_model_registry_activation_receipt(
        activation_command_id,
        req.model_dump(),
        tenant_id=str(user.tenant_id) if user.tenant_id else None,
        recorded_by=user.user_id,
    )
    if not (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("activation_command_id") == activation_command_id
        and result.get("receipt_state") == req.receipt_state
    ):
        raise HTTPException(
            status_code=503,
            detail="decision-service did not prove an authoritative registry receipt",
        )
    return result


class RegistryRollbackCommand(BaseModel):
    reason: str
    idempotency_key: str


@router.post("/api/v1/learning/activation-receipts/{activation_receipt_id}/rollback-command")
async def create_registry_rollback_command_bff(
    activation_receipt_id: str,
    req: RegistryRollbackCommand,
    user: UserSchema = Depends(require_permission(Permission.DECISION_MODEL_REGISTRY_EXECUTE)),
):
    from api.decision_service_client import create_model_registry_rollback_command

    result = await create_model_registry_rollback_command(
        activation_receipt_id,
        req.model_dump(),
        tenant_id=str(user.tenant_id) if user.tenant_id else None,
        requested_by=user.user_id,
    )
    if not (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("activation_receipt_id") == activation_receipt_id
        and result.get("command_state") == "queued"
    ):
        raise HTTPException(
            status_code=503,
            detail="decision-service did not prove an authoritative rollback command",
        )
    return result
