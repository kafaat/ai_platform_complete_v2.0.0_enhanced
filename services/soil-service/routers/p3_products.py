"""P3 governed soil imaging, analog, drainage and reclamation APIs."""

from __future__ import annotations

import hashlib
import json

import main
import p3_store
from fastapi import APIRouter, Header, HTTPException
from p3_products import (
    build_analog_field_product,
    build_drainage_assessment,
    build_mobile_visual_observation,
    build_reclamation_assessment,
    build_reclamation_economics,
)

from shared.contracts.soil.p3 import (
    AnalogFieldRequest,
    DrainageAssessmentRequest,
    MobileSoilImageRequest,
    ReclamationAssessmentRequest,
    ReclamationEconomicsRequest,
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


def _identity(payload):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


@router.post("/v1/fields/{field_id}/soil/mobile-images/analyze", status_code=201)
async def mobile(field_id: str, payload: MobileSoilImageRequest, x_agent_token: str = Header(None)):
    t = await _scope(field_id, payload, x_agent_token)
    p = build_mobile_visual_observation(payload)
    return await p3_store.save(
        main._pool,
        table="soil_visual_observations",
        id_column="visual_observation_id",
        product_id=p.visual_observation_id,
        tenant_id=t,
        field_id=field_id,
        product_type="mobile_soil_visual_observation",
        version=payload.model_version,
        identity_hash=_identity({"image_id": payload.image_id, "model": payload.model_version}),
        payload=p.model_dump(mode="json"),
    )


@router.post("/v1/fields/{field_id}/soil/analog-estimate", status_code=201)
async def analog(field_id: str, payload: AnalogFieldRequest, x_agent_token: str = Header(None)):
    t = await _scope(field_id, payload, x_agent_token)
    p = build_analog_field_product(payload)
    return await p3_store.save(
        main._pool,
        table="soil_analog_products",
        id_column="analog_product_id",
        product_id=p.product_id,
        tenant_id=t,
        field_id=field_id,
        product_type="analog_field_estimate",
        version=p.model_version,
        identity_hash=_identity(payload.model_dump(mode="json")),
        payload=p.model_dump(mode="json"),
    )


@router.post("/v1/fields/{field_id}/soil/drainage-assessment", status_code=201)
async def drainage(
    field_id: str, payload: DrainageAssessmentRequest, x_agent_token: str = Header(None)
):
    t = await _scope(field_id, payload, x_agent_token)
    p = build_drainage_assessment(payload)
    return await p3_store.save(
        main._pool,
        table="soil_drainage_assessments",
        id_column="drainage_assessment_id",
        product_id=p.product_id,
        tenant_id=t,
        field_id=field_id,
        product_type="drainage_assessment",
        version=p.assessment_version,
        identity_hash=_identity(payload.model_dump(mode="json")),
        payload=p.model_dump(mode="json"),
    )


@router.post("/v1/fields/{field_id}/soil/reclamation-assessment", status_code=201)
async def reclamation(
    field_id: str, payload: ReclamationAssessmentRequest, x_agent_token: str = Header(None)
):
    t = await _scope(field_id, payload, x_agent_token)
    p = build_reclamation_assessment(payload)
    return await p3_store.save(
        main._pool,
        table="soil_reclamation_assessments",
        id_column="reclamation_assessment_id",
        product_id=p.product_id,
        tenant_id=t,
        field_id=field_id,
        product_type="reclamation_assessment",
        version=p.assessment_version,
        identity_hash=_identity(payload.model_dump(mode="json")),
        payload=p.model_dump(mode="json"),
    )


@router.post("/v1/fields/{field_id}/soil/reclamation-economics", status_code=201)
async def economics(
    field_id: str, payload: ReclamationEconomicsRequest, x_agent_token: str = Header(None)
):
    t = await _scope(field_id, payload, x_agent_token)
    p = build_reclamation_economics(payload)
    return await p3_store.save(
        main._pool,
        table="soil_reclamation_economics",
        id_column="economics_product_id",
        product_id=p.product_id,
        tenant_id=t,
        field_id=field_id,
        product_type="reclamation_economics",
        version="reclamation-economics-v1",
        identity_hash=_identity(payload.model_dump(mode="json")),
        payload=p.model_dump(mode="json"),
    )


async def _current(field_id, token, table, msg):
    _auth(token)
    t = _tenant()
    await main._require_field_tenant(field_id)
    if not main._pool:
        raise HTTPException(503, "database unavailable")
    out = await p3_store.latest(main._pool, table=table, tenant_id=t, field_id=field_id)
    if not out:
        raise HTTPException(404, msg)
    return out


@router.get("/v1/fields/{field_id}/soil/mobile-images/latest")
async def get_mobile(field_id: str, x_agent_token: str = Header(None)):
    return await _current(
        field_id, x_agent_token, "soil_visual_observations", "visual observation not found"
    )


@router.get("/v1/fields/{field_id}/soil/analog-estimate")
async def get_analog(field_id: str, x_agent_token: str = Header(None)):
    return await _current(
        field_id, x_agent_token, "soil_analog_products", "analog estimate not found"
    )


@router.get("/v1/fields/{field_id}/soil/drainage-assessment")
async def get_drainage(field_id: str, x_agent_token: str = Header(None)):
    return await _current(
        field_id, x_agent_token, "soil_drainage_assessments", "drainage assessment not found"
    )


@router.get("/v1/fields/{field_id}/soil/reclamation-assessment")
async def get_reclamation(field_id: str, x_agent_token: str = Header(None)):
    return await _current(
        field_id, x_agent_token, "soil_reclamation_assessments", "reclamation assessment not found"
    )


@router.get("/v1/fields/{field_id}/soil/reclamation-economics")
async def get_economics(field_id: str, x_agent_token: str = Header(None)):
    return await _current(
        field_id, x_agent_token, "soil_reclamation_economics", "reclamation economics not found"
    )
