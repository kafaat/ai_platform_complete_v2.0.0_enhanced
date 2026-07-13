"""P2 governed spatial-soil product API."""

from __future__ import annotations

import main
import p2_store
from fastapi import APIRouter, Header, HTTPException
from p2_products import (
    build_bare_soil_composite,
    build_salinity_assessment,
    build_terrain_derivatives,
    build_texture_probability,
)

from shared.contracts.soil import (
    BareSoilCompositeRequest,
    SalinityAssessmentRequest,
    TerrainRequest,
    TextureProbabilityRequest,
)

router = APIRouter()


def _tenant():
    t = main._REQ_TENANT.get()
    if not t:
        raise HTTPException(400, "X-Tenant-Id required")
    return t


def _auth(token):
    main._require_service_token(token)


async def _scope(field_id, payload, token):
    _auth(token)
    t = _tenant()
    await main._require_field_tenant(field_id)
    if payload.tenant_id != t or payload.field_id != field_id:
        raise HTTPException(403, "scope mismatch")
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    return t


@router.post("/v1/fields/{field_id}/soil/bare-soil-composite", status_code=201)
async def bare(field_id: str, payload: BareSoilCompositeRequest, x_agent_token: str = Header(None)):
    t = await _scope(field_id, payload, x_agent_token)
    try:
        p = build_bare_soil_composite(payload)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return await p2_store.save_product(
        main._pool,
        table="soil_bare_composites",
        id_column="composite_id",
        product_id=p.product_id,
        tenant_id=t,
        field_id=field_id,
        product_type="bare_soil_composite",
        version=p.algorithm_version,
        geometry_hash=p.geometry_hash,
        payload=p.model_dump(mode="json"),
    )


@router.post("/v1/fields/{field_id}/soil/terrain-derivatives", status_code=201)
async def terrain(field_id: str, payload: TerrainRequest, x_agent_token: str = Header(None)):
    t = await _scope(field_id, payload, x_agent_token)
    p = build_terrain_derivatives(payload)
    return await p2_store.save_product(
        main._pool,
        table="soil_terrain_products",
        id_column="terrain_product_id",
        product_id=p.product_id,
        tenant_id=t,
        field_id=field_id,
        product_type="terrain_derivatives",
        version=f"{p.dem_version}:{p.algorithm_version}",
        geometry_hash=p.geometry_hash,
        payload=p.model_dump(mode="json"),
    )


@router.post("/v1/fields/{field_id}/soil/texture-probability", status_code=201)
async def texture(
    field_id: str, payload: TextureProbabilityRequest, x_agent_token: str = Header(None)
):
    t = await _scope(field_id, payload, x_agent_token)
    p = build_texture_probability(payload)
    return await p2_store.save_product(
        main._pool,
        table="soil_texture_products",
        id_column="texture_product_id",
        product_id=p.product_id,
        tenant_id=t,
        field_id=field_id,
        product_type="texture_probability",
        version=p.model_version,
        geometry_hash=p.geometry_hash,
        payload=p.model_dump(mode="json"),
    )


@router.post("/v1/fields/{field_id}/soil/salinity-assessment", status_code=201)
async def salinity(
    field_id: str, payload: SalinityAssessmentRequest, x_agent_token: str = Header(None)
):
    t = await _scope(field_id, payload, x_agent_token)
    p = build_salinity_assessment(payload)
    return await p2_store.save_product(
        main._pool,
        table="soil_salinity_products",
        id_column="salinity_product_id",
        product_id=p.product_id,
        tenant_id=t,
        field_id=field_id,
        product_type="salinity_gypsum_carbonate",
        version=p.model_version,
        geometry_hash=p.geometry_hash,
        payload=p.model_dump(mode="json"),
    )


async def _current(field_id, token, table, msg):
    _auth(token)
    t = _tenant()
    await main._require_field_tenant(field_id)
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    out = await p2_store.get_latest(main._pool, table=table, tenant_id=t, field_id=field_id)
    if not out:
        raise HTTPException(404, msg)
    return out


@router.get("/v1/fields/{field_id}/soil/bare-soil-composite")
async def get_bare(field_id: str, x_agent_token: str = Header(None)):
    return await _current(
        field_id, x_agent_token, "soil_bare_composites", "bare soil composite not found"
    )


@router.get("/v1/fields/{field_id}/soil/terrain-derivatives")
async def get_terrain(field_id: str, x_agent_token: str = Header(None)):
    return await _current(
        field_id, x_agent_token, "soil_terrain_products", "terrain derivatives not found"
    )


@router.get("/v1/fields/{field_id}/soil/texture-probability")
async def get_texture(field_id: str, x_agent_token: str = Header(None)):
    return await _current(
        field_id, x_agent_token, "soil_texture_products", "texture product not found"
    )


@router.get("/v1/fields/{field_id}/soil/salinity-assessment")
async def get_salinity(field_id: str, x_agent_token: str = Header(None)):
    return await _current(
        field_id, x_agent_token, "soil_salinity_products", "salinity assessment not found"
    )
