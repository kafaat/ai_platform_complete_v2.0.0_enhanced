"""RS-6 signal anomaly lifecycle and RS-7 ground-verification bridge."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
import main
from anomaly_engine import detect_signals
from anomaly_requests import (
    DetectRequest,
    TransitionRequest,
    VerificationCompletion,
    VerificationRequest,
)
from anomaly_runtime import store as _store
from anomaly_store import AnomalyNotFound, InvalidTransition
from fastapi import APIRouter, Depends, Header, HTTPException
from ground_verification_bridge import GroundVerificationBridge

router = APIRouter()
_bridge = GroundVerificationBridge()
_TASK_CALLBACK_TOKEN = os.getenv("TASK_SERVICE_CALLBACK_TOKEN", "")


async def _baselines(field_id: str, request: DetectRequest, token: str) -> list[dict[str, Any]]:
    # Call the engine route's dependencies through indicators directly to avoid an
    # HTTP self-call when running as one process.
    import routers.baselines as baseline_router

    tenant_id = main._tenant_from_claims(main._verify_claims(token))
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{baseline_router.INDICATORS_SERVICE_URL}/v1/fields/{quote(field_id, safe='')}/observation-timeline",
                params={"season_id": request.season_id, "indicators": request.indicator},
                headers={"X-Tenant-Id": tenant_id, "Authorization": f"Bearer {token.credentials}"},
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
            max_gap_days=request.max_gap_days,
            as_of=datetime.now(UTC),
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
    existing = await _store.list(tenant_id, field_id, request.season_id) if signals else []
    for signal in signals:
        payload = {
            **signal.to_dict(),
            "tenant_id": tenant_id,
            "field_id": field_id,
            "season_id": request.season_id,
            "geometry_ref": None,
            "status": "detected",
            "detector_model_ref": "urn:sahool:model:signal_detector_v2",
        }
        # A baseline policy upgrade may select a different reference for the
        # same acquisition/direction. Reuse its tenant-scoped lifecycle rather
        # than duplicating already requested/confirmed scouting work.
        record = next(
            (
                item
                for item in existing
                if item["payload"].get("primary_observation_ref") == signal.primary_observation_ref
                and item["payload"].get("signal_type") == signal.signal_type
            ),
            None,
        )
        if record is None:
            record = await _store.upsert_detected(payload)
        record["current_evaluation"] = {**signal.to_dict(), "anomaly_ref": record["anomaly_ref"]}
        if (
            request.auto_request_verification
            and signal.verification_requirement == "required"
            and record["status"] in {"detected", "triaged"}
            and not record.get("task_ref")
        ):
            try:
                key = hashlib.sha256(f"{record['anomaly_ref']}|verification".encode()).hexdigest()
                task = await _bridge.create_scouting_task(
                    anomaly=record["payload"],
                    authorization=authorization,
                    idempotency_key=key,
                )
                record = await _store.transition(
                    record["anomaly_ref"],
                    "verification_requested",
                    expected_version=record["aggregate_version"],
                    task_ref=task.task_ref,
                    patch={"task_ref": task.task_ref},
                    tenant_id=tenant_id,
                )
            except RuntimeError as exc:
                record["verification_bridge_error"] = str(exc)
        created.append(record)
    return {
        "field_id": field_id,
        "season_id": request.season_id,
        "indicator": request.indicator,
        "anomalies": created,
        "evaluation_status": "assessed" if comparisons else "insufficient_qualified_history",
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
        "anomalies": await _store.list(tenant_id, field_id, season_id),
    }


@router.post("/v1/anomalies/{anomaly_ref:path}/transition")
async def transition_anomaly(
    anomaly_ref: str,
    request: TransitionRequest,
    token: str = Depends(main.security),
):
    tenant_id = main._tenant_from_claims(main._verify_claims(token))
    try:
        record = await _store.get(anomaly_ref, tenant_id=tenant_id)
        if record["tenant_id"] != tenant_id:
            raise AnomalyNotFound(anomaly_ref)
        return await _store.transition(
            anomaly_ref,
            request.target_status,
            expected_version=request.expected_version,
            patch={"transition_reason_codes": request.reason_codes},
            tenant_id=tenant_id,
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
        record = await _store.get(anomaly_ref, tenant_id=tenant_id)
        if record["tenant_id"] != tenant_id:
            raise AnomalyNotFound(anomaly_ref)
        key = hashlib.sha256(f"{anomaly_ref}|verification".encode()).hexdigest()
        task = await _bridge.create_scouting_task(
            anomaly=record["payload"],
            authorization=authorization,
            idempotency_key=key,
        )
        return await _store.transition(
            anomaly_ref,
            "verification_requested",
            expected_version=request.expected_version,
            task_ref=task.task_ref,
            patch={"task_ref": task.task_ref},
            tenant_id=tenant_id,
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
        record = await _store.get(anomaly_ref, tenant_id=tenant_id)
        if record["tenant_id"] != tenant_id:
            raise AnomalyNotFound(anomaly_ref)
        if record.get("task_ref") and record["task_ref"] != request.task_ref:
            raise InvalidTransition("verification_task_ref_mismatch")
        if any(str(e.tenant_id) != tenant_id for e in request.evidence):
            raise HTTPException(403, "verification_evidence_tenant_mismatch")
        patch = {
            "verification_evidence": [e.model_dump(mode="json") for e in request.evidence],
            "verification_result": request.verification_result,
            "verification_evidence_refs": request.evidence_refs,
            "disposition_reason_codes": request.reason_codes,
            "verification_completed_at": request.completed_at.astimezone(UTC).isoformat(),
        }
        if record["status"] == request.verification_result == "confirmed":
            previous = record["payload"]
            if (
                not record.get("task_ref")
                or record["task_ref"] != request.task_ref
                or previous.get("verification_evidence")
                or set(previous.get("verification_evidence_refs") or [])
                != set(request.evidence_refs)
            ):
                raise InvalidTransition("legacy_evidence_recovery_binding_mismatch")
            completed = previous.get("verification_completed_at")
            if completed:
                try:
                    original_completed = datetime.fromisoformat(
                        str(completed).replace("Z", "+00:00")
                    )
                except (ValueError, TypeError) as exc:
                    raise InvalidTransition("legacy_completion_timestamp_invalid") from exc
                if original_completed.tzinfo is None or any(
                    e.captured_at > original_completed for e in request.evidence
                ):
                    raise InvalidTransition("legacy_evidence_postdates_confirmation")
            # The completion timestamp/reasons remain the original persisted
            # values; recovery supplies metadata only, never a new confirmation.
            patch = {
                "verification_evidence": patch["verification_evidence"],
                "verification_metadata_recovered_at": datetime.now(UTC).isoformat(),
            }
        return await _store.transition(
            anomaly_ref,
            request.verification_result,
            expected_version=request.expected_version,
            patch=patch,
            tenant_id=tenant_id,
        )
    except AnomalyNotFound as exc:
        raise HTTPException(404, "anomaly not found") from exc
    except InvalidTransition as exc:
        raise HTTPException(409, str(exc)) from exc
