from __future__ import annotations

import main
from fastapi import APIRouter, Depends, Header, HTTPException
from post_execution_bridge import PostExecutionBridge
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()
_bridge = PostExecutionBridge()


class FollowUpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    season_id: str
    execution_request_id: str
    days_after: int = Field(default=5, ge=1, le=30)
    indicators: list[str] = Field(default_factory=lambda: ["ndvi", "ndmi"])


class OutcomeVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_plan_id: str
    dispatch_authorization_id: str
    decision_id: str
    receipt_id: str
    verification_state: str
    evidence_snapshot_id: str
    actual: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    idempotency_key: str


class LearningAttributionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str
    feature_set_id: str | None = None
    label: str
    weight: float = Field(default=1.0, gt=0, le=1)
    evidence_snapshot_id: str
    idempotency_key: str
    metadata: dict = Field(default_factory=dict)


@router.post("/v1/fields/{field_id}/post-execution-observations")
async def schedule_post_execution_observation(
    field_id: str,
    request: FollowUpRequest,
    authorization: str = Header(..., alias="Authorization"),
    token: str = Depends(main.security),
):
    tenant = main._tenant_from_claims(main._verify_claims(token))
    try:
        return await _bridge.schedule_follow_up(
            field_id=field_id,
            season_id=request.season_id,
            execution_request_id=request.execution_request_id,
            authorization=authorization,
            tenant_id=tenant,
            days_after=request.days_after,
            indicators=request.indicators,
        )
    except RuntimeError as exc:
        raise HTTPException(424, str(exc)) from exc


@router.post("/v1/execution-requests/{execution_request_id}/remote-sensing-outcome")
async def verify_remote_sensing_outcome(
    execution_request_id: str,
    request: OutcomeVerificationRequest,
    authorization: str = Header(..., alias="Authorization"),
    verified_by: str = Header(..., alias="X-Verified-By"),
    token: str = Depends(main.security),
):
    tenant = main._tenant_from_claims(main._verify_claims(token))
    try:
        return await _bridge.verify_outcome(
            execution_request_id=execution_request_id,
            authorization=authorization,
            tenant_id=tenant,
            verified_by=verified_by,
            payload=request.model_dump(),
        )
    except RuntimeError as exc:
        raise HTTPException(424, str(exc)) from exc


@router.post("/v1/outcomes/{outcome_id}/remote-sensing-attribution")
async def attribute_remote_sensing_outcome(
    outcome_id: str,
    request: LearningAttributionRequest,
    authorization: str = Header(..., alias="Authorization"),
    attributed_by: str = Header(..., alias="X-Attributed-By"),
    token: str = Depends(main.security),
):
    tenant = main._tenant_from_claims(main._verify_claims(token))
    payload = request.model_dump()
    payload["attribution_method"] = "verified_outcome"
    try:
        return await _bridge.attribute_learning(
            outcome_id=outcome_id,
            authorization=authorization,
            tenant_id=tenant,
            attributed_by=attributed_by,
            payload=payload,
        )
    except RuntimeError as exc:
        raise HTTPException(424, str(exc)) from exc
