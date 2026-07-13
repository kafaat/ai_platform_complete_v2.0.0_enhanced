"""P1 governed soil product API."""

from __future__ import annotations

import main
import p1_store
import soil_store
from fastapi import APIRouter, Header, HTTPException
from p1_products import build_hydraulic_profile, build_sampling_plan, build_water_profile

from shared.contracts.soil import (
    IrrigationWaterSample,
    SamplingPlanRequest,
    SoilGridsSpatialProduct,
    SoilObservation,
    SoilObservationQuality,
    SoilObservationSource,
)

router = APIRouter()


def tenant():
    t = main._REQ_TENANT.get()
    if not t:
        raise HTTPException(400, "X-Tenant-Id required")
    return t


def auth(token):
    main._require_service_token(token)


@router.post("/v1/fields/{field_id}/soil/soilgrids-spatial", status_code=201)
async def ingest_soilgrids(
    field_id: str, payload: SoilGridsSpatialProduct, x_agent_token: str = Header(None)
):
    auth(x_agent_token)
    t = tenant()
    await main._require_field_tenant(field_id)
    if payload.tenant_id != t or payload.field_id != field_id:
        raise HTTPException(403, "scope mismatch")
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    pid = await p1_store.save_spatial(main._pool, payload)
    obs = []
    for lyr in payload.layers:
        value = lyr.mean
        o = SoilObservation(
            tenant_id=t,
            field_id=field_id,
            property=lyr.property,
            value=value,
            unit=lyr.unit,
            depth_from_cm=lyr.depth_from_cm,
            depth_to_cm=lyr.depth_to_cm,
            observed_at=payload.generated_at,
            source_type=SoilObservationSource.SOILGRIDS,
            source_id=pid,
            quality_status=SoilObservationQuality.ACCEPTED,
            confidence=0.45,
            idempotency_key=f"soilgrids:{payload.dataset_version}:{payload.geometry_hash}:{lyr.property}:{lyr.depth_from_cm}:{lyr.depth_to_cm}",
            provenance={
                "dataset_version": payload.dataset_version,
                "geometry_hash": payload.geometry_hash,
                "product_id": pid,
                "uncertainty": {"p05": lyr.p05, "p95": lyr.p95, "native": lyr.uncertainty},
                "evidence_class": "modelled",
            },
        )
        obs.append(o)
        await soil_store.persist_observation(main._pool, o)
    snap = await soil_store.rebuild_snapshot_locked(main._pool, tenant_id=t, field_id=field_id)
    return {
        "product_id": pid,
        "observation_ids": [o.observation_id for o in obs],
        "profile_hash": snap.profile_hash,
        "evidence_class": "modelled",
    }


@router.post("/v1/fields/{field_id}/soil/sampling-plans", status_code=201)
async def create_plan(
    field_id: str, payload: SamplingPlanRequest, x_agent_token: str = Header(None)
):
    auth(x_agent_token)
    t = tenant()
    await main._require_field_tenant(field_id)
    if payload.tenant_id != t or payload.field_id != field_id:
        raise HTTPException(403, "scope mismatch")
    p = build_sampling_plan(payload)
    if main._pool:
        await p1_store.save_sampling(main._pool, p)
    else:
        raise HTTPException(503, "database unavailable")
    return p


@router.post("/v1/soil/sampling-plans/{plan_id}/approve")
async def approve_plan(
    plan_id: str, x_actor_id: str = Header(...), x_agent_token: str = Header(None)
):
    auth(x_agent_token)
    t = tenant()
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    row = await p1_store.approve_sampling(main._pool, t, plan_id, x_actor_id)
    if not row:
        raise HTTPException(409, "plan not found or not draft")
    return row["payload"]


@router.post("/v1/fields/{field_id}/soil/hydraulic-profile/rebuild")
async def rebuild_hydraulic(field_id: str, x_agent_token: str = Header(None)):
    auth(x_agent_token)
    t = tenant()
    await main._require_field_tenant(field_id)
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    snap = await soil_store.get_current_snapshot(main._pool, tenant_id=t, field_id=field_id)
    if not snap:
        raise HTTPException(404, "soil profile not found")
    p = build_hydraulic_profile(snap)
    return await p1_store.save_hydraulic(main._pool, p)


@router.post("/v1/soil/irrigation-water/samples", status_code=201)
async def water_sample(payload: IrrigationWaterSample, x_agent_token: str = Header(None)):
    auth(x_agent_token)
    t = tenant()
    if payload.tenant_id != t:
        raise HTTPException(403, "tenant mismatch")
    if payload.field_id:
        await main._require_field_tenant(payload.field_id)
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    return await p1_store.save_water(main._pool, payload, build_water_profile(payload))


@router.get("/v1/fields/{field_id}/soil/soilgrids-spatial")
async def current_soilgrids(field_id: str, x_agent_token: str = Header(None)):
    auth(x_agent_token)
    t = tenant()
    await main._require_field_tenant(field_id)
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    out = await p1_store.get_latest(main._pool, t, "soil_spatial_products", "field_id", field_id)
    if not out:
        raise HTTPException(404, "soilgrids spatial product not found")
    return out


@router.get("/v1/fields/{field_id}/soil/sampling-plans/current")
async def current_sampling(field_id: str, x_agent_token: str = Header(None)):
    auth(x_agent_token)
    t = tenant()
    await main._require_field_tenant(field_id)
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    out = await p1_store.get_latest(main._pool, t, "soil_sampling_plans", "field_id", field_id)
    if not out:
        raise HTTPException(404, "sampling plan not found")
    return out


@router.get("/v1/fields/{field_id}/soil/hydraulic-profile")
async def current_hydraulic(field_id: str, x_agent_token: str = Header(None)):
    auth(x_agent_token)
    t = tenant()
    await main._require_field_tenant(field_id)
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    out = await p1_store.get_latest(main._pool, t, "soil_hydraulic_profiles", "field_id", field_id)
    if not out:
        raise HTTPException(404, "hydraulic profile not found")
    return out


@router.get("/v1/soil/irrigation-water/sources/{source_id}/profile")
async def current_water(source_id: str, x_agent_token: str = Header(None)):
    auth(x_agent_token)
    t = tenant()
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    out = await p1_store.get_latest(
        main._pool, t, "irrigation_water_profiles", "source_id", source_id
    )
    if not out:
        raise HTTPException(404, "irrigation water profile not found")
    return out
