"""Soil-sampling plan copies and plan-point origin resolution (gap P6).

soil-service owns ``soil_sampling_plan_copies`` (v273). The platform forwards the AI planner's
plans here from its service-authenticated advice event, and its lab-sample route asks this
router to resolve a plan point before it stores a sample. Both routes need the service token and
the trusted ``X-Tenant-Id``; a plan is looked up by tenant, field and plan id, so another
tenant's plan reads exactly like an unknown one.
"""

from __future__ import annotations

import uuid
from typing import Any

import main
import plan_copy_store
from fastapi import APIRouter, Header, HTTPException
from plan_origin import OriginRefused, normalize_plan_copy, resolve_origin
from pydantic import BaseModel, Field

router = APIRouter()


class PlanCopiesIn(BaseModel):
    plans: list[dict[str, Any]] = Field(min_length=1, max_length=10)
    source: str = Field(min_length=1, max_length=64)


class OriginRequest(BaseModel):
    point_id: str = Field(min_length=1, max_length=80)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    gps_accuracy_m: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    deviation_reason: str | None = Field(default=None, max_length=200)
    claimed: dict[str, Any] | None = None


def _tenant() -> str:
    tenant = main._REQ_TENANT.get()
    if not tenant:
        raise HTTPException(400, "X-Tenant-Id required")
    try:
        return str(uuid.UUID(tenant))
    except ValueError as exc:
        raise HTTPException(400, "X-Tenant-Id must be a tenant UUID") from exc


@router.post("/v1/fields/{field_id}/soil/sampling-plan-copies", status_code=201)
async def store_plan_copies(
    field_id: str, payload: PlanCopiesIn, x_agent_token: str = Header(None)
):
    main._require_service_token(x_agent_token)
    tenant = _tenant()
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    # A copy is written only for a field this tenant is proven to own.
    if await main._require_field_tenant(field_id) is None:
        raise HTTPException(404, "field not found")
    copies = [c for c in (normalize_plan_copy(p, field_id) for p in payload.plans) if c]
    counts = {"stored": 0, "unchanged": 0, "conflicting": 0}
    if copies:
        counts = await plan_copy_store.save_plan_copies(
            main._pool, tenant_id=tenant, copies=copies, source=payload.source
        )
    return {**counts, "skipped": len(payload.plans) - len(copies)}


@router.post("/v1/fields/{field_id}/soil/sampling-plan-copies/{plan_id}/origin")
async def resolve_plan_origin(
    field_id: str, plan_id: str, payload: OriginRequest, x_agent_token: str = Header(None)
):
    main._require_service_token(x_agent_token)
    tenant = _tenant()
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    copy = await plan_copy_store.get_plan_copy(
        main._pool, tenant_id=tenant, field_id=field_id, plan_id=plan_id
    )
    if copy is None:
        raise HTTPException(404, {"code": "sampling_plan_not_found", "plan_id": plan_id})
    try:
        return resolve_origin(
            plan_id=copy["plan_id"],
            plan_digest_value=copy["plan_digest"],
            sample_points=copy["sample_points"],
            point_id=payload.point_id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            gps_accuracy_m=payload.gps_accuracy_m,
            deviation_reason=payload.deviation_reason,
            claimed=payload.claimed,
        )
    except OriginRefused as exc:
        raise HTTPException(exc.status, exc.detail()) from exc
