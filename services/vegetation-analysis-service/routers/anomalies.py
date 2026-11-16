"""RS-6 signal anomaly lifecycle and RS-7 ground-verification bridge."""

from __future__ import annotations

import hashlib
import logging
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
from anomaly_store import _ALLOWED_TRANSITIONS, AnomalyNotFound, InvalidTransition
from fastapi import APIRouter, Depends, Header, HTTPException
from ground_verification_bridge import GroundVerificationBridge

logger = logging.getLogger(__name__)
router = APIRouter()
_bridge = GroundVerificationBridge()
_TASK_CALLBACK_TOKEN = os.getenv("TASK_SERVICE_CALLBACK_TOKEN", "")
# The lifecycle states that may move to verification_requested (anomaly_store._ALLOWED_TRANSITIONS).
_VERIFICATION_SOURCES = frozenset(
    status
    for status, targets in _ALLOWED_TRANSITIONS.items()
    if "verification_requested" in targets
)


def _check_verification_allowed(record: dict[str, Any], expected_version: int) -> None:
    """Refuse a verification request before any field task is created.

    W1-20 made the bridge store a real task in field-management-service, so a request the
    lifecycle would refuse must be refused *before* the bridge call; otherwise a closed anomaly
    (resolved, confirmed, rejected) leaves an orphan pending scouting task behind, and the
    one-task-per-anomaly index then blocks any later correct task.

    Re-verification after ``inconclusive`` would reuse this anomaly's deterministic key and get
    the old, finished task back as a replay, so nobody would be dispatched. Until the task-side
    re-verification contract exists (W2-15), it is refused instead of pointing at the old task.
    """
    status = record.get("status")
    if status not in _VERIFICATION_SOURCES:
        raise InvalidTransition(f"invalid_transition:{status}->verification_requested")
    if record.get("aggregate_version") != expected_version:
        raise InvalidTransition("aggregate_version_conflict")
    if record.get("task_ref"):
        raise InvalidTransition("reverification_not_supported:anomaly_already_has_task")


def _lifecycle_conflict(exc: InvalidTransition, task_ref: str) -> dict[str, Any]:
    """The stored field task could not be attached to the anomaly's reservation.

    Since SCOUTING-ANOMALY-VERIFY-RACE-ORPHAN-TASK-01 the verification is reserved against the
    expected version *before* the task is dispatched, and while the reservation is pending no
    other transition (a resolve, a verification result) may move the anomaly. The attach can
    therefore only lose to another holder of the same reservation, or to a store failure; the
    reservation then stays pending, the anomaly cannot be closed, and a retry with the original
    expected version replays the same deterministic Idempotency-Key and attaches the same task.
    """
    return {
        "code": "verification_lifecycle_conflict",
        "reason": str(exc),
        "task_ref": task_ref,
        "task_attached": False,
    }


class VerificationDispatchFailed(Exception):
    """The bridge stored no confirmed task; says whether the reservation was given back."""

    def __init__(self, reason: str, *, reservation: str, record: dict[str, Any]) -> None:
        super().__init__(reason)
        self.record = record  # the anomaly as this request last wrote or read it
        self.detail = {
            "code": "verification_dispatch_failed",
            "reason": reason,
            "reservation": reservation,
        }


class VerificationAttachConflict(Exception):
    def __init__(self, exc: InvalidTransition, task_ref: str) -> None:
        super().__init__(str(exc))
        self.detail = _lifecycle_conflict(exc, task_ref)


def _verification_key(anomaly_ref: str) -> str:
    return hashlib.sha256(f"{anomaly_ref}|verification".encode()).hexdigest()


def _bridge_outcome_is_ambiguous(exc: RuntimeError) -> bool:
    """True when the task service may have stored the task although the call failed.

    A transport failure or a 5xx can come after the owner committed the task. Giving the
    reservation back then would reopen the orphan window, so it is kept pending: the anomaly
    stays un-closable until a retry replays the same key and attaches the task. Every other
    failure (missing configuration, tenant mismatch, a 4xx refusal, a reply that is not a stored
    task) is known to have stored nothing, so the prior state is restored.
    """
    reason = str(exc)
    if reason == "task_service_unavailable":
        return True
    if reason.startswith("task_service_rejected:"):
        code = reason.rsplit(":", 1)[1]
        return not (code.isdigit() and 400 <= int(code) < 500)
    return False


def _reservation_replay(record: dict[str, Any], expected_version: int, key: str) -> str | None:
    """Is this request a replay of an earlier one for the same reservation?

    Returns ``"attached"`` (the earlier request finished: hand back the same record and task),
    ``"pending"`` (the earlier request reserved but did not attach: resume its dispatch with the
    same key) or ``None`` (a fresh request).
    """
    reservation = (record.get("payload") or {}).get("verification_reservation")
    if (
        record.get("status") != "verification_requested"
        or not isinstance(reservation, dict)
        or reservation.get("idempotency_key") != key
        or reservation.get("reserved_from_version") != expected_version
    ):
        return None
    if reservation.get("state") == "attached" and record.get("task_ref"):
        return "attached"
    if reservation.get("state") == "pending" and not record.get("task_ref"):
        return "pending"
    return None


async def _reserve_and_dispatch(
    anomaly_ref: str, record: dict[str, Any], expected_version: int, tenant_id: str
) -> dict[str, Any]:
    """Reserve the verification, dispatch the field task, then attach it.

    The reservation is taken against ``expected_version`` atomically in the anomaly store
    before the task exists, so a concurrent resolve can no longer strand a pending task.
    """
    key = _verification_key(anomaly_ref)
    replay = _reservation_replay(record, expected_version, key)
    if replay == "attached":
        return record
    if replay == "pending":
        reserved, owns_reservation = record, False
    else:
        _check_verification_allowed(record, expected_version)
        reserved = await _store.reserve_verification(
            anomaly_ref,
            expected_version=expected_version,
            idempotency_key=key,
            tenant_id=tenant_id,
        )
        owns_reservation = True
    try:
        task = await _bridge.create_scouting_task(
            anomaly=reserved["payload"],
            tenant_id=tenant_id,
            idempotency_key=key,
        )
    except RuntimeError as exc:
        state, latest = "pending", reserved
        # Only the request that took the reservation gives it back, and only when the task
        # service is known to have stored nothing; a resumed replay never releases it under
        # a concurrent holder.
        if owns_reservation and not _bridge_outcome_is_ambiguous(exc):
            try:
                latest = await _store.release_verification_reservation(
                    anomaly_ref,
                    expected_version=reserved["aggregate_version"],
                    idempotency_key=key,
                    reason=str(exc),
                    tenant_id=tenant_id,
                )
                state = "released"
            except Exception as release_exc:  # the reservation stays pending; a retry resumes it
                logger.warning(
                    "Verification reservation release failed for %s (%s)",
                    anomaly_ref,
                    type(release_exc).__name__,
                )
        raise VerificationDispatchFailed(str(exc), reservation=state, record=latest) from exc
    try:
        return await _store.attach_verification_task(
            anomaly_ref,
            expected_version=reserved["aggregate_version"],
            idempotency_key=key,
            task_ref=task.task_ref,
            tenant_id=tenant_id,
        )
    except InvalidTransition as exc:
        # A concurrent replay of the same reservation may have attached the same task first.
        current = await _store.get(anomaly_ref, tenant_id=tenant_id)
        if current.get("task_ref") == task.task_ref:
            return current
        raise VerificationAttachConflict(exc, task.task_ref) from exc


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
                record = {
                    **await _reserve_and_dispatch(
                        record["anomaly_ref"], record, record["aggregate_version"], tenant_id
                    ),
                    "current_evaluation": record["current_evaluation"],
                }
            except VerificationDispatchFailed as exc:
                record = {
                    **exc.record,
                    "current_evaluation": record["current_evaluation"],
                    "verification_bridge_error": exc.detail["reason"],
                    "verification_reservation_outcome": exc.detail["reservation"],
                }
            except VerificationAttachConflict as exc:
                record["verification_lifecycle_conflict"] = exc.detail
            except InvalidTransition as exc:
                # Another request moved the anomaly before the reservation: report it on this
                # anomaly and keep evaluating the others, instead of failing the whole call.
                record["verification_lifecycle_conflict"] = {
                    "code": "verification_lifecycle_conflict",
                    "reason": str(exc),
                    "task_ref": None,
                    "task_attached": False,
                }
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
        return await _reserve_and_dispatch(anomaly_ref, record, request.expected_version, tenant_id)
    except VerificationAttachConflict as exc:
        raise HTTPException(409, exc.detail) from exc
    except VerificationDispatchFailed as exc:
        raise HTTPException(424, exc.detail) from exc
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
