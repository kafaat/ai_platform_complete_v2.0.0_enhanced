from __future__ import annotations

import main
import p4_store
from fastapi import APIRouter, Header, HTTPException
from p5_certification import build_calibration, build_learning_manifest, certify, evaluate_promotion

from shared.contracts.soil.p5 import (
    FieldValidationRecord,
    ProductionCertificationRecord,
    RegionalCalibrationArtifact,
)

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


@router.post("/v1/fields/{field_id}/soil/validations", status_code=201)
async def create_validation(
    field_id: str, payload: FieldValidationRecord, x_agent_token: str = Header(None)
):
    t = await _ctx(field_id, x_agent_token)
    if payload.tenant_id != t or payload.field_id != field_id:
        raise HTTPException(403, "scope mismatch")
    return await p4_store.save(
        main._pool,
        table="soil_field_validations",
        id_column="validation_id",
        record_id=payload.validation_id,
        tenant_id=t,
        field_id=field_id,
        extra={
            "governorate": payload.governorate,
            "crop": payload.crop,
            "campaign_id": payload.campaign_id,
            "accepted": payload.accepted,
        },
        payload=payload.model_dump(mode="json"),
    )


@router.post("/v1/soil/calibrations/build", status_code=201)
async def create_calibration(payload: dict, x_agent_token: str = Header(None)):
    main._require_service_token(x_agent_token)
    t = _tenant()
    rows = [FieldValidationRecord.model_validate(x) for x in payload.get("validations", [])]
    if any(r.tenant_id != t for r in rows):
        raise HTTPException(403, "scope mismatch")
    item = build_calibration(
        tenant_id=t,
        governorate=payload["governorate"],
        crop=payload.get("crop"),
        product_type=payload["product_type"],
        dataset_version=payload["dataset_version"],
        model_version=payload["model_version"],
        records=rows,
        minimum_samples=int(payload.get("minimum_samples", 20)),
    )
    return await p4_store.save(
        main._pool,
        table="soil_regional_calibrations",
        id_column="calibration_id",
        record_id=item.calibration_id,
        tenant_id=t,
        field_id="regional",
        extra={
            "governorate": item.governorate,
            "crop": item.crop,
            "product_type": item.product_type,
            "status": item.status,
        },
        payload=item.model_dump(mode="json"),
    )


@router.post("/v1/soil/calibrations/{calibration_id}/evaluate")
async def evaluate_calibration(
    calibration_id: str, payload: RegionalCalibrationArtifact, x_agent_token: str = Header(None)
):
    main._require_service_token(x_agent_token)
    t = _tenant()
    if payload.tenant_id != t or payload.calibration_id != calibration_id:
        raise HTTPException(403, "scope mismatch")
    return evaluate_promotion(payload).model_dump(mode="json")


@router.post("/v1/soil/production-certifications", status_code=201)
async def create_certification(
    payload: ProductionCertificationRecord, x_agent_token: str = Header(None)
):
    main._require_service_token(x_agent_token)
    t = _tenant()
    if payload.tenant_id != t:
        raise HTTPException(403, "scope mismatch")
    item = certify(payload)
    return await p4_store.save(
        main._pool,
        table="soil_production_certifications",
        id_column="certification_id",
        record_id=item.certification_id,
        tenant_id=t,
        field_id="release",
        extra={
            "release_ref": item.release_ref,
            "environment": item.environment,
            "certified": item.certified,
        },
        payload=item.model_dump(mode="json"),
    )


@router.post("/v1/soil/learning-datasets", status_code=201)
async def create_learning_dataset(payload: dict, x_agent_token: str = Header(None)):
    main._require_service_token(x_agent_token)
    t = _tenant()
    item = build_learning_manifest(
        tenant_id=t,
        name=payload["name"],
        version=payload["version"],
        learning_rows=payload.get("learning_rows", []),
        feature_schema_version=payload["feature_schema_version"],
        target_schema_version=payload["target_schema_version"],
    )
    return await p4_store.save(
        main._pool,
        table="soil_learning_datasets",
        id_column="dataset_id",
        record_id=item.dataset_id,
        tenant_id=t,
        field_id="dataset",
        extra={
            "name": item.name,
            "version": item.version,
            "eligible_for_training": item.eligible_for_training,
        },
        payload=item.model_dump(mode="json"),
    )
