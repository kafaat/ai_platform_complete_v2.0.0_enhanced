"""P4 soil governance and closed-loop endpoints."""

from __future__ import annotations

import main
import p4_store
from fastapi import APIRouter, Header, HTTPException
from p4_governance import POLICIES, build_learning, evaluate_action

from shared.contracts.soil.p4 import SoilExecutionRecord, SoilOutcomeRecord, SoilVerificationRecord

router = APIRouter()


def _tenant():
    t = main._REQ_TENANT.get()
    if not t:
        raise HTTPException(400, "X-Tenant-Id required")
    return t


async def _ctx(field_id, token):
    main._require_service_token(token)
    t = _tenant()
    await main._require_field_tenant(field_id)
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    return t


@router.get("/v1/soil/action-policies")
async def policies(x_agent_token: str = Header(None)):
    main._require_service_token(x_agent_token)
    return {"policies": [p.model_dump(mode="json") for p in POLICIES.values()]}


@router.post("/v1/fields/{field_id}/soil/actions/{action_type}/evaluate")
async def evaluate(
    field_id: str, action_type: str, payload: dict, x_agent_token: str = Header(None)
):
    await _ctx(field_id, x_agent_token)
    return evaluate_action(
        payload.get("soil_profile") or {},
        action_type,
        water_profile_approved=bool(payload.get("water_profile_approved")),
        drainage_verified=bool(payload.get("drainage_verified")),
    ).model_dump(mode="json")


@router.post("/v1/fields/{field_id}/soil/executions", status_code=201)
async def create_execution(
    field_id: str, payload: SoilExecutionRecord, x_agent_token: str = Header(None)
):
    t = await _ctx(field_id, x_agent_token)
    if payload.tenant_id != t or payload.field_id != field_id:
        raise HTTPException(403, "scope mismatch")
    if not payload.approved_by:
        raise HTTPException(422, "approved_by required")
    return await p4_store.save(
        main._pool,
        table="soil_execution_records",
        id_column="execution_id",
        record_id=payload.execution_id,
        tenant_id=t,
        field_id=field_id,
        extra={
            "decision_id": payload.decision_id,
            "action_type": payload.action_type,
            "profile_hash": payload.profile_hash,
        },
        payload=payload.model_dump(mode="json"),
    )


@router.post("/v1/fields/{field_id}/soil/verifications", status_code=201)
async def create_verification(
    field_id: str, payload: SoilVerificationRecord, x_agent_token: str = Header(None)
):
    t = await _ctx(field_id, x_agent_token)
    if payload.tenant_id != t or payload.field_id != field_id:
        raise HTTPException(403, "scope mismatch")
    return await p4_store.save(
        main._pool,
        table="soil_verification_records",
        id_column="verification_id",
        record_id=payload.verification_id,
        tenant_id=t,
        field_id=field_id,
        extra={"execution_id": payload.execution_id},
        payload=payload.model_dump(mode="json"),
    )


@router.post("/v1/fields/{field_id}/soil/outcomes", status_code=201)
async def create_outcome(
    field_id: str, payload: SoilOutcomeRecord, x_agent_token: str = Header(None)
):
    t = await _ctx(field_id, x_agent_token)
    if payload.tenant_id != t or payload.field_id != field_id:
        raise HTTPException(403, "scope mismatch")
    return await p4_store.save(
        main._pool,
        table="soil_outcome_records",
        id_column="outcome_id",
        record_id=payload.outcome_id,
        tenant_id=t,
        field_id=field_id,
        extra={"execution_id": payload.execution_id, "verification_id": payload.verification_id},
        payload=payload.model_dump(mode="json"),
    )


@router.post("/v1/fields/{field_id}/soil/learning-attributions", status_code=201)
async def create_learning(field_id: str, payload: dict, x_agent_token: str = Header(None)):
    t = await _ctx(field_id, x_agent_token)
    execution = SoilExecutionRecord.model_validate(payload["execution"])
    outcome = SoilOutcomeRecord.model_validate(payload["outcome"])
    if execution.tenant_id != t or execution.field_id != field_id or outcome.tenant_id != t:
        raise HTTPException(403, "scope mismatch")
    item = build_learning(outcome, execution, payload.get("soil_profile") or {})
    return await p4_store.save(
        main._pool,
        table="soil_learning_attributions",
        id_column="learning_id",
        record_id=item.learning_id,
        tenant_id=t,
        field_id=field_id,
        extra={
            "outcome_id": item.outcome_id,
            "execution_id": item.execution_id,
            "profile_hash": item.source_profile_hash,
            "eligible_for_training": item.eligible_for_training,
        },
        payload=item.model_dump(mode="json"),
    )


@router.get("/v1/fields/{field_id}/soil/closed-loop")
async def closed_loop(field_id: str, x_agent_token: str = Header(None)):
    t = await _ctx(field_id, x_agent_token)
    return {
        k: await p4_store.list_field(main._pool, table=v, tenant_id=t, field_id=field_id)
        for k, v in {
            "executions": "soil_execution_records",
            "verifications": "soil_verification_records",
            "outcomes": "soil_outcome_records",
            "learning": "soil_learning_attributions",
        }.items()
    }
