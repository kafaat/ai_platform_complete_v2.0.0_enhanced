"""Durable imagery requests: authenticated tenant, authoritative receipt, explicit status."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import follow_up_runtime as runtime
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, Response
from follow_up_store import RequestConflict

from shared.contracts.imagery_followup import (
    ImageryFollowUpRequest,
    request_digest,
    request_identity,
)
from shared.security.access_tokens import verify_access_token

router = APIRouter()
FieldId = Annotated[str, Path(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")]


def authenticated_tenant(
    authorization: str = Header(...), x_tenant_id: str | None = Header(None)
) -> str:
    try:
        scheme, bearer = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            raise ValueError("bearer_required")
        tenant = str(UUID(verify_access_token(bearer)["tenant_id"]))
    except (ValueError, KeyError) as exc:
        raise HTTPException(401, "invalid_access_token") from exc
    if x_tenant_id is not None and x_tenant_id != tenant:
        raise HTTPException(403, "tenant_header_mismatch")
    return tenant


def public_status(row: dict) -> dict:
    payload = row["request_payload"]
    return {
        "request_id": row["request_id"],
        "field_id": row["field_id"],
        "status": row["status"],
        "due_at": row["due_at"],
        "expires_at": row["expires_at"],
        "attempts": row["attempts"],
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "next_attempt_at": row.get("next_attempt_at"),
        "time_basis": payload["time_basis"],
        "receipt_id": payload["receipt_id"],
        "reason_code": row["reason_code"],
        "result": row["result_payload"],
        "physical_execution_verified": False,
        "outcome_verified": False,
    }


@router.post("/v1/fields/{field_id}/imagery-ingestion-requests", status_code=202)
async def create_follow_up(
    field_id: FieldId,
    body: ImageryFollowUpRequest,
    request: Request,
    response: Response,
    tenant: str = Depends(authenticated_tenant),
):
    if (
        not getattr(request.app.state, "follow_up_ready", False)
        or tenant not in runtime.configured_tenants()
    ):
        raise HTTPException(503, "follow_up_worker_not_enabled_for_tenant")
    identity = request_identity(tenant, field_id, body.execution_request_id)
    digest = request_digest(body)
    try:
        row = await runtime.store.get(tenant, identity)
        if row is not None:
            if row["request_hash"] != digest:
                raise RequestConflict("follow_up_request_payload_mismatch")
        else:
            payload, due, expires = await runtime.admission_payload(tenant, field_id, body)
            row = await runtime.store.enqueue(
                tenant=tenant,
                request_id=identity,
                field_id=field_id,
                request_hash=digest,
                payload=payload,
                due_at=due,
                expires_at=expires,
            )
    except RequestConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — no persistence ⇒ no 202
        raise HTTPException(503, "follow_up_persistence_unavailable") from exc
    response.headers["Location"] = f"/v1/fields/{field_id}/imagery-ingestion-requests/{identity}"
    response.headers["Retry-After"] = "30"
    return public_status(row)


@router.get("/v1/fields/{field_id}/imagery-ingestion-requests/{request_id}")
async def get_follow_up(
    field_id: FieldId, request_id: str, tenant: str = Depends(authenticated_tenant)
):
    try:
        row = await runtime.store.get(tenant, request_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, "follow_up_persistence_unavailable") from exc
    if row is None or row["field_id"] != field_id:
        raise HTTPException(404, "follow_up_not_found")
    return public_status(row)
