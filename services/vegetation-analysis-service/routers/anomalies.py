"""RS-6 signal anomaly lifecycle and RS-7 ground-verification bridge."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

import httpx
import main
from anomaly_engine import detect_signals
from anomaly_store import AnomalyNotFound, AnomalyStore, InvalidTransition
from fastapi import APIRouter, Depends, Header, HTTPException
from ground_verification_bridge import GroundVerificationBridge
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()
_store = AnomalyStore()
_bridge = GroundVerificationBridge()
_TASK_CALLBACK_TOKEN = os.getenv("TASK_SERVICE_CALLBACK_TOKEN", "")


class DetectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    season_id: str = Field(min_length=1, max_length=128)
    indicator: str = Field(default="ndvi", min_length=1, max_length=64)
    current_stage: str | None = Field(default=None, max_length=128)
    stage_by_observation: dict[str, str] = Field(default_factory=dict)
    max_history: int = Field(default=12, ge=1, le=60)
    min_deviation_percent: Decimal = Field(default=Decimal("7"), ge=0, le=100)
    auto_request_verification: bool = False


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    target_status: Literal["triaged", "resolved"]
    reason_codes: list[str] = Field(default_factory=list)


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    priority: str | None = Field(default=None, max_length=32)


class VerificationCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    task_ref: str = Field(min_length=1, max_length=256)
    verification_result: Literal["confirmed", "rejected", "inconclusive"]
    evidence_refs: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    completed_at: datetime


async def _baselines(field_id: str, request: DetectRequest, token: str) -> list[dict[str, Any]]:
    import routers.baselines as baseline_router

    tenant_id = main._tenant_from_claims(main._verify_claims(token))
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{baseline_router.INDICATORS_SERVICE_URL}/v1/fields/{field_id}/observation-timeline",
                params={"season_id": request.season_id, "indicators": request.indicator},
                headers={"X-Tenant-Id": tenant_id},
            )
        if response.status_code != 200:
            raise HTTPException(424, "canonical observation timeline unavailable")
        timeline = response.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(424, "canonical observation timeline unavailable") from exc
    from baseline_engine import build_baselines

    return [
        item.to_dict()
        for item in build_baselines(
            field_id=field_id,
            indicator=request.indicator,
            entries=list(timeline.get("entries") or []),
            current_stage=request.current_stage,
            stage_by_observation=request.stage_by_observation,
            max_history=request.max_history,
        )
    ]


@router.post("/v1/fields/{field_id}/signal-anomalies/detect")
async def detect_signal_anomalies(
    field_id: str,
    request: DetectRequest,
    authorization: str = Header(..., alias="Authorization"),
    token: str = Depends(main.security),
):
    claims = main._verify_claims(token)
    tenant_id = main._tenant_from_claims(claims)
    comparisons = await _baselines(field_id, request, token)
    signals = detect_signals(
        field_id=field_id,
        indicator=request.indicator,
        comparisons=comparisons,
        min_deviation_percent=request.min_deviation_percent,
    )
    created = []
    for signal in signals:
        payload = {
            **signal.to_dict(),
            "tenant_id": tenant_id,
            "field_id": field_id,
            "season_id": request.season_id,
            "geometry_ref": None,
            "status": "detected",
            "detector_model_ref": "urn:sahool:model:signal_detector_v1",
        }
        record = _store.upsert_detected(payload)
        if request.auto_request_verification and signal.verification_requirement == "required":
            try:
                key = hashlib.sha256(f"{record['anomaly_ref']}|verification".encode()).hexdigest()
                task = await _bridge.create_scouting_task(
                    anomaly=record["payload"],
                    authorization=authorization,
                    idempotency_key=key,
                )
                record = _store.transition(
                    record["anomaly_ref"],
                    "verification_requested",
                    expected_version=record["aggregate_version"],
                    task_ref=task.task_ref,
                    patch={"task_ref": task.task_ref},
                )
            except RuntimeError as exc:
                record["verification_bridge_error"] = str(exc)
        created.append(record)
    return {
        "field_id": field_id,
        "season_id": request.season_id,
        "indicator": request.indicator,
        "anomalies": created,
        "signal_only": True,
        "diagnosis_emitted": False,
    }


@router.get("/v1/fields/{field_id}/signal-anomalies")
async def list_signal_anomalies(
    field_id: str,
    season_id: str,
    token: str = Depends(main.security),
):
    tenant_id = main._tenant_from_claims(main._verify_claims(token))
    return {
        "field_id": field_id,
        "season_id": season_id,
        "anomalies": _store.list(tenant_id, field_id, season_id),
    }


@router.post("/v1/anomalies/{anomaly_ref:path}/transition")
async def transition_anomaly(
    anomaly_ref: str,
    request: TransitionRequest,
    token: str = Depends(main.security),
):
    tenant_id = main._tenant_from_claims(main._verify_claims(token))
    try:
        record = _store.get(anomaly_ref)
        if record["tenant_id"] != tenant_id:
            raise AnomalyNotFound(anomaly_ref)
        return _store.transition(
            anomaly_ref,
            request.target_status,
            expected_version=request.expected_version,
            patch={"transition_reason_codes": request.reason_codes},
        )
    except AnomalyNotFound as exc:
        raise HTTPException(404, "anomaly not found") from exc
    except InvalidTransition as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/v1/anomalies/{anomaly_ref:path}/verification-requests")
async def request_ground_verification(
    anomaly_ref: str,
    request: VerificationRequest,
    authorization: str = Header(..., alias="Authorization"),
    token: str = Depends(main.security),
):
    tenant_id = main._tenant_from_claims(main._verify_claims(token))
    try:
        record = _store.get(anomaly_ref)
        if record["tenant_id"] != tenant_id:
            raise AnomalyNotFound(anomaly_ref)
        key = hashlib.sha256(f"{anomaly_ref}|verification".encode()).hexdigest()
        task = await _bridge.create_scouting_task(
            anomaly=record["payload"],
            authorization=authorization,
            idempotency_key=key,
        )
        return _store.transition(
            anomaly_ref,
            "verification_requested",
            expected_version=request.expected_version,
            task_ref=task.task_ref,
            patch={"task_ref": task.task_ref},
        )
    except AnomalyNotFound as exc:
        raise HTTPException(404, "anomaly not found") from exc
    except InvalidTransition as exc:
        raise HTTPException(409, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(424, str(exc)) from exc


@router.post("/v1/anomalies/{anomaly_ref:path}/verification-results")
async def accept_verification_result(
    anomaly_ref: str,
    request: VerificationCompletion,
    task_service_token: str = Header(..., alias="X-Task-Service-Token"),
    token: str = Depends(main.security),
):
    if not _TASK_CALLBACK_TOKEN:
        raise HTTPException(503, "task verification callback is not configured")
    if not secrets.compare_digest(task_service_token, _TASK_CALLBACK_TOKEN):
        raise HTTPException(403, "invalid task-service callback token")
    tenant_id = main._tenant_from_claims(main._verify_claims(token))
    try:
        record = _store.get(anomaly_ref)
        if record["tenant_id"] != tenant_id:
            raise AnomalyNotFound(anomaly_ref)
        if record.get("task_ref") and record["task_ref"] != request.task_ref:
            raise InvalidTransition("verification_task_ref_mismatch")
        patch = {
            "verification_result": request.verification_result,
            "verification_evidence_refs": request.evidence_refs,
            "disposition_reason_codes": request.reason_codes,
            "verification_completed_at": request.completed_at.astimezone(UTC).isoformat(),
        }
        return _store.transition(
            anomaly_ref,
            request.verification_result,
            expected_version=request.expected_version,
            patch=patch,
        )
    except AnomalyNotFound as exc:
        raise HTTPException(404, "anomaly not found") from exc
    except InvalidTransition as exc:
        raise HTTPException(409, str(exc)) from exc
