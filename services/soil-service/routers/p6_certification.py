from __future__ import annotations

import main
import p4_store
from fastapi import APIRouter, Header, HTTPException
from p6_certification import evaluate_run, verify_manifest

from shared.contracts.soil.p6 import CertificationPolicy, RuntimeCertificationRun

router = APIRouter()


def _tenant():
    tenant = main._REQ_TENANT.get()
    if not tenant:
        raise HTTPException(400, "X-Tenant-Id required")
    return tenant


@router.post("/v1/soil/runtime-certifications/evaluate", status_code=201)
async def evaluate_certification(
    payload: RuntimeCertificationRun, x_agent_token: str = Header(None)
):
    main._require_service_token(x_agent_token)
    tenant = _tenant()
    if payload.tenant_id != tenant:
        raise HTTPException(403, "scope mismatch")
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    item = evaluate_run(payload, CertificationPolicy())
    return await p4_store.save(
        main._pool,
        table="soil_runtime_certification_runs",
        id_column="run_id",
        record_id=item.run_id,
        tenant_id=tenant,
        field_id="release",
        extra={
            "release_ref": item.release_ref,
            "environment": item.environment,
            "status": item.status,
            "manifest_sha256": item.manifest_sha256,
        },
        payload=item.model_dump(mode="json"),
    )


@router.post("/v1/soil/runtime-certifications/{run_id}/verify")
async def verify_certification(
    run_id: str, payload: RuntimeCertificationRun, x_agent_token: str = Header(None)
):
    main._require_service_token(x_agent_token)
    tenant = _tenant()
    if payload.tenant_id != tenant or payload.run_id != run_id:
        raise HTTPException(403, "scope mismatch")
    return {"run_id": run_id, "manifest_valid": verify_manifest(payload), "status": payload.status}


@router.get("/v1/soil/runtime-certifications/{run_id}")
async def get_certification(run_id: str, x_agent_token: str = Header(None)):
    main._require_service_token(x_agent_token)
    tenant = _tenant()
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    item = await p4_store.get(
        main._pool,
        table="soil_runtime_certification_runs",
        id_column="run_id",
        record_id=run_id,
        tenant_id=tenant,
    )
    if item is None:
        raise HTTPException(404, "certification run not found")
    return item
