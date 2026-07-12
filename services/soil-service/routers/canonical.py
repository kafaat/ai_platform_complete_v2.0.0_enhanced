"""Canonical soil observations and SoilProfileSnapshot read model."""

from __future__ import annotations

import main
import soil_store
from fastapi import APIRouter, Header, HTTPException, Query

from shared.contracts.soil import SoilObservation

router = APIRouter()


def _tenant_required() -> str:
    tenant_id = main._REQ_TENANT.get()
    if not tenant_id:
        raise HTTPException(400, "X-Tenant-Id required")
    return tenant_id


@router.post("/v1/soil/observations", status_code=201)
async def create_observation(observation: SoilObservation, x_agent_token: str = Header(None)):
    main._require_service_token(x_agent_token)
    tenant_id = _tenant_required()
    if observation.tenant_id != tenant_id:
        raise HTTPException(403, "observation tenant mismatch")
    await main._require_field_tenant(observation.field_id)
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    inserted = await soil_store.persist_observation(main._pool, observation)
    snapshot = await soil_store.rebuild_snapshot_locked(
        main._pool, tenant_id=tenant_id, field_id=observation.field_id
    )
    return {
        "status": "created" if inserted else "duplicate",
        "observation_id": observation.observation_id,
        "profile_id": snapshot.profile_id,
        "profile_hash": snapshot.profile_hash,
    }


@router.get("/v1/fields/{field_id}/soil/observations")
async def observations(
    field_id: str,
    property: str | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    x_agent_token: str = Header(None),
):
    main._require_service_token(x_agent_token)
    tenant_id = _tenant_required()
    await main._require_field_tenant(field_id)
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    return await soil_store.list_observations(
        main._pool, tenant_id=tenant_id, field_id=field_id, property_name=property, limit=limit
    )


@router.post("/v1/fields/{field_id}/soil/profile/rebuild")
async def rebuild_profile(field_id: str, x_agent_token: str = Header(None)):
    main._require_service_token(x_agent_token)
    tenant_id = _tenant_required()
    await main._require_field_tenant(field_id)
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    snapshot = await soil_store.rebuild_snapshot_locked(
        main._pool, tenant_id=tenant_id, field_id=field_id
    )
    return snapshot


@router.get("/v1/fields/{field_id}/soil/profile")
async def current_profile(field_id: str, x_agent_token: str = Header(None)):
    main._require_service_token(x_agent_token)
    tenant_id = _tenant_required()
    await main._require_field_tenant(field_id)
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    snapshot = await soil_store.get_current_snapshot(
        main._pool, tenant_id=tenant_id, field_id=field_id
    )
    if snapshot is None:
        raise HTTPException(404, "soil profile not found")
    return snapshot


@router.get("/v1/fields/{field_id}/soil/profile/history")
async def profile_history(
    field_id: str,
    limit: int = Query(50, ge=1, le=500),
    x_agent_token: str = Header(None),
):
    main._require_service_token(x_agent_token)
    tenant_id = _tenant_required()
    await main._require_field_tenant(field_id)
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    return await soil_store.get_snapshot_history(
        main._pool, tenant_id=tenant_id, field_id=field_id, limit=limit
    )


from datetime import datetime  # noqa: E402

import evidence_adapters  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from shared.contracts.soil import SoilObservationSource  # noqa: E402


class EvidenceBatchIn(BaseModel):
    source_type: SoilObservationSource
    source_id: str = Field(min_length=1, max_length=256)
    properties: dict[str, object]
    observed_at: datetime | None = None
    depth_from_cm: float = Field(default=0, ge=0)
    depth_to_cm: float = Field(default=30, gt=0)
    approved: bool = False
    procedure_id: str | None = None
    provenance: dict[str, object] = Field(default_factory=dict)


@router.post("/v1/fields/{field_id}/soil/evidence", status_code=201)
async def ingest_typed_evidence(
    field_id: str, payload: EvidenceBatchIn, x_agent_token: str = Header(None)
):
    """Canonical adapter boundary for lab, SoilGrids, smartphone, analog and field evidence."""
    main._require_service_token(x_agent_token)
    tenant_id = _tenant_required()
    await main._require_field_tenant(field_id)
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    observations = evidence_adapters.observations_from_properties(
        tenant_id=tenant_id,
        field_id=field_id,
        source_type=payload.source_type,
        source_id=payload.source_id,
        properties=payload.properties,
        observed_at=payload.observed_at,
        depth_from_cm=payload.depth_from_cm,
        depth_to_cm=payload.depth_to_cm,
        approved=payload.approved,
        procedure_id=payload.procedure_id,
        provenance=payload.provenance,
    )
    created = 0
    for observation in observations:
        created += int(await soil_store.persist_observation(main._pool, observation))
    snapshot = await soil_store.rebuild_snapshot_locked(
        main._pool, tenant_id=tenant_id, field_id=field_id
    )
    return {
        "status": "accepted",
        "created": created,
        "duplicates": len(observations) - created,
        "observation_ids": [o.observation_id for o in observations],
        "profile_id": snapshot.profile_id,
        "profile_hash": snapshot.profile_hash,
    }
