"""Default-off owner callback for reviewed anomaly verification.

Field-management owns the visit, link, review and outbox. This receiver owns only
the anomaly transition and a delivery receipt in its existing aggregate payload.
The public JWT callback remains unchanged. A receipt is not proof of a cause,
an agricultural intervention, a learning label or its benefit.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from anomaly_requests import VerificationCompletion
from anomaly_runtime import store as _store
from anomaly_store import AnomalyNotFound, InvalidTransition
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from shared.contracts.remote_sensing.verification_delivery import (
    canonical_completion_digest,
    canonical_completion_payload,
    flag_enabled,
    verification_request_binding,
)
from shared.security.service_tenant_assertion import TenantAssertionError, verify_tenant_assertion

INSPECTION_BRIDGE_CHANNEL = "inspection_owner_bridge"
router = APIRouter()
_CALLER = "field-management-service"
_KEY = re.compile(r"^[A-Za-z0-9_.:-]{16,128}$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_ANOMALY_REF = re.compile(r"^urn:sahool:anomaly:[A-Za-z0-9_-]+$")
_GEOMETRY_REF = re.compile(r"^urn:sahool:geometry:[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class VerificationCaller:
    tenant_id: str
    request_id: str


def verification_caller(
    request: Request,
    task_service_token: str | None = Header(None, alias="X-Task-Service-Token"),
    tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    service_name: str | None = Header(None, alias="X-Service-Name"),
    request_id: str | None = Header(None, alias="X-Request-Id"),
    tenant_assertion: str | None = Header(None, alias="X-Tenant-Assertion"),
) -> VerificationCaller:
    """Require dedicated credentials and the exact encoded method/path/tenant.

    The assertion expires under the shared verifier's 60-second window. GET is
    read-only. POST additionally binds its body and key to the signed request id,
    and its durable receipt makes a repeated request safe across process restarts.
    No process-memory nonce cache is presented as a distributed replay fence.
    """
    if not flag_enabled(os.getenv("VEGETATION_VERIFICATION_BRIDGE_ENABLED", "0")):
        raise HTTPException(404, "verification_bridge_disabled")
    # A dedicated token: TASK_SERVICE_CALLBACK_TOKEN is the only service factor of the legacy
    # /v1/anomalies/.../verification-results route, so sharing it would hand field-management
    # (which also receives the user's Authorization) both factors of that unreviewed path.
    expected_token = os.getenv("VEGETATION_VERIFICATION_SERVICE_TOKEN", "")
    legacy_token = os.getenv("TASK_SERVICE_CALLBACK_TOKEN", "")
    key = os.getenv("VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY", "")
    key_id = os.getenv("VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY_ID", "current")
    if not expected_token or len(key) < 32 or not key_id:
        raise HTTPException(503, "verification_service_credentials_unconfigured")
    if legacy_token and hmac.compare_digest(expected_token.encode(), legacy_token.encode()):
        raise HTTPException(503, "verification_service_token_not_dedicated")
    if not hmac.compare_digest((task_service_token or "").encode(), expected_token.encode()):
        raise HTTPException(403, "invalid_task_service_token")
    if service_name != _CALLER or not _REQUEST_ID.fullmatch(request_id or ""):
        raise HTTPException(403, "verification_caller_scope_invalid")
    try:
        canonical_tenant = str(UUID(tenant_id or ""))
        # The shared v2 format uses ':' as a separator: an anomaly URN must be
        # percent-encoded in the signed HTTP path, exactly as sent on the wire.
        raw_path = request.scope["raw_path"].decode("ascii")
        if ":" in raw_path or "?" in raw_path:
            raise TenantAssertionError("verification_path_must_be_encoded")
        verify_tenant_assertion(
            tenant_assertion or "",
            {key_id: key},
            _CALLER,
            canonical_tenant,
            expected_method=request.method,
            expected_path=raw_path,
            expected_request_id=request_id or "",
        )
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise HTTPException(403, "invalid_verification_tenant_assertion") from exc
    return VerificationCaller(canonical_tenant, request_id or "")


def _snapshot_digest(record: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _qualified_record(record: dict, tenant_id: str, anomaly_ref: str) -> dict:
    """Validate stored scope before exposing it as an owner snapshot."""
    if record.get("tenant_id") != tenant_id or record.get("anomaly_ref") != anomaly_ref:
        raise AnomalyNotFound(anomaly_ref)
    payload = record.get("payload")
    if not isinstance(payload, dict) or type(record.get("aggregate_version")) is not int:
        raise HTTPException(503, "verification_anomaly_record_invalid")
    if record["aggregate_version"] < 1 or not _ANOMALY_REF.fullmatch(anomaly_ref):
        raise HTTPException(503, "verification_anomaly_record_invalid")
    for name in ("anomaly_ref", "tenant_id", "field_id", "season_id"):
        if not isinstance(record.get(name), str) or not record[name]:
            raise HTTPException(503, "verification_anomaly_record_invalid")
        if payload.get(name) != record[name]:
            raise HTTPException(503, "verification_anomaly_scope_inconsistent")
    geometry = payload.get("geometry_ref")
    if geometry is not None and (
        not isinstance(geometry, str) or not _GEOMETRY_REF.fullmatch(geometry)
    ):
        raise HTTPException(503, "verification_geometry_reference_invalid")
    if payload.get("task_ref") not in (None, record.get("task_ref")):
        raise HTTPException(503, "verification_anomaly_task_inconsistent")
    if payload.get("status") not in (None, record.get("status")):
        raise HTTPException(503, "verification_anomaly_status_inconsistent")
    try:
        _snapshot_digest(record)
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(503, "verification_anomaly_snapshot_invalid") from exc
    return record


async def _read_record(anomaly_ref: str, tenant_id: str) -> dict:
    record = await _store.get(anomaly_ref, tenant_id=tenant_id)
    record = _qualified_record(record, tenant_id, anomaly_ref)
    _validated_receipt(record)
    return record


def _response(record: dict, *, replayed: bool) -> dict:
    return {
        "persisted": True,
        "replayed": replayed,
        "anomaly": record,
        "verification_delivery": record["payload"]["verification_delivery"],
    }


def _validated_receipt(record: dict) -> dict | None:
    """Validate a persisted receipt before either GET reconciliation or POST replay."""
    if "verification_delivery" not in record["payload"]:
        return None
    receipt = record["payload"]["verification_delivery"]
    if not isinstance(receipt, dict):
        raise HTTPException(503, "verification_delivery_receipt_invalid")
    try:
        original = receipt["original_completion"]
        if (
            not isinstance(original, dict)
            or original.keys() != VerificationCompletion.model_fields.keys()
        ):
            raise ValueError("stored_completion_fields_invalid")
        body = canonical_completion_payload(
            VerificationCompletion.model_validate(original).model_dump(mode="json")
        )
        evidence_refs = [item["evidence_ref"] for item in body["evidence"]]
        if (
            original != body
            or receipt.get("request_digest") != canonical_completion_digest(body)
            or not isinstance(receipt.get("idempotency_key"), str)
            or not _KEY.fullmatch(receipt["idempotency_key"])
            or not isinstance(receipt.get("request_snapshot_digest"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", receipt["request_snapshot_digest"])
            or type(receipt.get("expected_version")) is not int
            or type(receipt.get("accepted_version")) is not int
            or len(set(evidence_refs)) != len(evidence_refs)
            or len(set(body["evidence_refs"])) != len(body["evidence_refs"])
            or set(evidence_refs) != set(body["evidence_refs"])
            or any(item["tenant_id"] != record["tenant_id"] for item in body["evidence"])
        ):
            raise ValueError("stored_receipt_invalid")
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise HTTPException(503, "verification_delivery_receipt_invalid") from exc
    payload = record["payload"]
    expected = body["expected_version"]
    if (
        receipt.get("expected_version") != expected
        or receipt.get("accepted_version") != expected + 1
        or receipt.get("completed_at") != body["completed_at"]
        or receipt.get("original_completion") != body
        or record["aggregate_version"] < receipt["accepted_version"]
        or record.get("task_ref") != body["task_ref"]
    ):
        raise HTTPException(503, "verification_delivery_receipt_inconsistent")
    # At the accepted version, the completion and its payload must agree. A
    # later owner transition may legitimately replace disposition_reason_codes
    # (for example when resolving the anomaly). Reconcile that later state using
    # the immutable original completion in the receipt, not mutable live metadata.
    if record["aggregate_version"] == receipt["accepted_version"] and (
        payload.get("verification_result") != body["verification_result"]
        or payload.get("verification_completed_at") != body["completed_at"]
        or payload.get("verification_evidence_refs") != body["evidence_refs"]
        or payload.get("verification_evidence") != body["evidence"]
        or payload.get("disposition_reason_codes") != body["reason_codes"]
    ):
        raise HTTPException(503, "verification_delivery_receipt_inconsistent")
    return receipt


def _replayed(record: dict, key: str, digest: str, body: dict) -> dict | None:
    receipt = _validated_receipt(record)
    if receipt is None:
        return None
    if receipt["idempotency_key"] != key:
        raise InvalidTransition("verification_delivery_already_recorded")
    if receipt["request_digest"] != digest:
        raise InvalidTransition("verification_idempotency_key_reused_with_different_request")
    if receipt["original_completion"] != body:
        raise HTTPException(503, "verification_delivery_receipt_inconsistent")
    return _response(record, replayed=True)


@router.get("/internal/anomalies/{anomaly_ref:path}/verification-context")
async def verification_context(
    anomaly_ref: str, caller: VerificationCaller = Depends(verification_caller)
):
    """A current persisted aggregate and its digest, not a new verification decision."""
    try:
        record = await _read_record(anomaly_ref, caller.tenant_id)
    except AnomalyNotFound as exc:
        raise HTTPException(404, "anomaly not found") from exc
    return {
        "schema_version": "sahool.verification-context/v1",
        "persisted": True,
        "anomaly": record,
        "snapshot_digest": _snapshot_digest(record),
    }


@router.post("/internal/anomalies/{anomaly_ref:path}/verification-results")
async def verification_result(
    anomaly_ref: str,
    request: VerificationCompletion,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    caller: VerificationCaller = Depends(verification_caller),
):
    """Store exactly one completion and delivery receipt in the owner's existing CAS."""
    if not _KEY.fullmatch(idempotency_key or ""):
        raise HTTPException(422, "verification_idempotency_key_invalid")
    key = idempotency_key or ""
    body = canonical_completion_payload(request.model_dump(mode="json"))
    digest = canonical_completion_digest(body)
    signed_binding = caller.request_id.rsplit(".", 1)
    if len(signed_binding) != 2 or not hmac.compare_digest(
        signed_binding[1], verification_request_binding(key, digest)
    ):
        raise HTTPException(403, "verification_request_body_binding_mismatch")
    if any(str(e.tenant_id) != caller.tenant_id for e in request.evidence):
        raise HTTPException(403, "verification_evidence_tenant_mismatch")
    # The original DTO requires evidence metadata for confirmed. Preserve that
    # and refuse mismatched/duplicate references for every internal disposition.
    refs = [e.evidence_ref for e in request.evidence]
    if (
        len(set(refs)) != len(refs)
        or len(set(request.evidence_refs)) != len(request.evidence_refs)
        or set(refs) != set(request.evidence_refs)
    ):
        raise HTTPException(422, "verification_evidence_reference_mismatch")
    try:
        record = await _read_record(anomaly_ref, caller.tenant_id)
        if replay := _replayed(record, key, digest, body):
            return replay
        if not record.get("task_ref") or record["task_ref"] != request.task_ref:
            raise InvalidTransition("verification_task_ref_mismatch_or_unbound")
        if record["aggregate_version"] != request.expected_version:
            raise InvalidTransition("aggregate_version_conflict")
        if record["status"] != "verification_requested":
            raise InvalidTransition("verification_not_requested")
        receipt = {
            "idempotency_key": key,
            "request_digest": digest,
            "expected_version": request.expected_version,
            "accepted_version": request.expected_version + 1,
            "completed_at": body["completed_at"],
            "original_completion": body,
            "request_snapshot_digest": _snapshot_digest(record),
        }
        patch = {
            "verification_evidence": body["evidence"],
            "verification_result": body["verification_result"],
            "verification_evidence_refs": body["evidence_refs"],
            "disposition_reason_codes": body["reason_codes"],
            "verification_completed_at": body["completed_at"],
            "verification_delivery": receipt,
            # Stamped by this receiver, not taken from the sender: RS-8 refuses to diagnose
            # from it. A confirmed/not-confirmed field check is not a diagnosis.
            "verification_channel": INSPECTION_BRIDGE_CHANNEL,
        }
        try:
            updated = await _store.transition(
                anomaly_ref,
                request.verification_result,
                expected_version=request.expected_version,
                patch=patch,
                tenant_id=caller.tenant_id,
            )
        except InvalidTransition:
            # A concurrent exact request may have committed first. Read the
            # owner's receipt; never retry with a guessed newer version.
            current = await _read_record(anomaly_ref, caller.tenant_id)
            if replay := _replayed(current, key, digest, body):
                return replay
            raise
        return _response(_qualified_record(updated, caller.tenant_id, anomaly_ref), replayed=False)
    except AnomalyNotFound as exc:
        raise HTTPException(404, "anomaly not found") from exc
    except InvalidTransition as exc:
        raise HTTPException(409, str(exc)) from exc
