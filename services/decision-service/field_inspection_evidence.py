"""Read the field-task owner's current proof before recording inspection success.

Accepted delivery proves task creation, not completed inspection. The owner readback
is independent of browser/adapter claims. It certifies the recorded review at the
observation time, not a physical event or a transaction spanning both services.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import UUID

import httpx

_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class OwnerEvidenceError(Exception):
    """A bounded reason; upstream bodies and tokens never become public errors."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


async def read_owner_proof(tenant_id: str, execution_request_id: str) -> dict[str, Any]:
    base = os.getenv("FIELD_MANAGEMENT_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv("FIELD_INSPECTION_PROOF_TOKEN", "").strip()
    try:
        parsed = urlsplit(base)
        configured = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and bool(token)
        )
    except ValueError:
        configured = False
    if not configured:
        raise OwnerEvidenceError("field_inspection_owner_unconfigured")
    url = base + "/internal/field-tasks/execution-proofs/" + quote(execution_request_id, safe="")
    try:
        async with httpx.AsyncClient(
            timeout=3.0, trust_env=False, follow_redirects=False
        ) as client:
            response = await client.get(
                url,
                headers={
                    "X-Tenant-Id": tenant_id,
                    "X-Field-Inspection-Proof-Token": token,
                },
            )
    except httpx.HTTPError as exc:
        raise OwnerEvidenceError("field_inspection_owner_unavailable") from exc
    if response.status_code in {404, 409}:
        raise OwnerEvidenceError("field_inspection_proof_not_current")
    if response.status_code in {401, 403}:
        raise OwnerEvidenceError("field_inspection_owner_rejected")
    if response.status_code != 200:
        raise OwnerEvidenceError("field_inspection_owner_unavailable")
    if len(response.content) > 65_536:
        raise OwnerEvidenceError("field_inspection_proof_invalid")
    try:
        proof = response.json()
    except ValueError as exc:
        raise OwnerEvidenceError("field_inspection_proof_invalid") from exc
    if not isinstance(proof, dict):
        raise OwnerEvidenceError("field_inspection_proof_invalid")
    return proof


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _same_json(left: Any, right: Any) -> bool:
    try:
        options = {"sort_keys": True, "separators": (",", ":"), "allow_nan": False}
        return json.dumps(left, **options) == json.dumps(right, **options)
    except (ValueError, TypeError):
        return False


async def verify_owner_evidence(
    *, tenant_id: str, execution_request_id: str, verified_by: str, source: Any, payload: Any
) -> str | None:
    """Refuse missing/stale/mismatched evidence, including an idempotent re-attestation."""
    try:
        proof = await read_owner_proof(tenant_id, execution_request_id)
    except OwnerEvidenceError as exc:
        return exc.reason
    if proof.get("schema") != "sahool.field-inspection-execution-proof/v1":
        return "field_inspection_proof_invalid"
    if any(
        proof.get(key) is not True for key in ("authoritative", "persisted", "current", "completed")
    ):
        return "field_inspection_proof_not_current"
    expected = {
        "tenant_id": tenant_id,
        "execution_request_id": execution_request_id,
        "execution_plan_id": source.get("execution_plan_id"),
        "dispatch_authorization_id": source.get("dispatch_authorization_id"),
        "decision_id": source.get("decision_id"),
        "receipt_id": source.get("receipt_id"),
        "correlation_id": source.get("correlation_id"),
        "field_id": source.get("field_id"),
    }
    if any(not value or str(proof.get(key, "")) != str(value) for key, value in expected.items()):
        return "field_inspection_proof_binding_mismatch"
    receipt = _object(source.get("receipt_payload"))
    if (
        receipt.get("provider") != "field-management-service"
        or receipt.get("operation_type") != "field_inspection"
        or not proof.get("task_id")
        or receipt.get("provider_task_id") != proof["task_id"]
        or proof.get("task_ref") != "urn:sahool:task:" + str(proof["task_id"])
    ):
        return "field_inspection_receipt_binding_mismatch"
    for key in (
        "execution_request_id",
        "decision_id",
        "execution_plan_id",
        "dispatch_authorization_id",
        "correlation_id",
        "field_id",
        "pin_id",
        "task_ref",
    ):
        if not proof.get(key) or str(receipt.get(key, "")) != str(proof[key]):
            return "field_inspection_receipt_binding_mismatch"
    command = _object(source.get("command_payload"))
    inspection = _object(command.get("inspection"))
    if (
        not proof.get("pin_id")
        or source.get("target_id") != proof["pin_id"]
        or inspection.get("pin_id") != proof["pin_id"]
        or command.get("field_id") != proof["field_id"]
    ):
        return "field_inspection_proof_binding_mismatch"
    reviewer, inspector = proof.get("reviewer_id"), proof.get("inspector_id")
    if (
        not isinstance(reviewer, str)
        or not reviewer
        or not isinstance(inspector, str)
        or not inspector
        or reviewer == inspector
        or reviewer != verified_by
        or proof.get("verified_by") != verified_by
    ):
        return "field_inspection_reviewer_mismatch"
    if (
        type(proof.get("evidence_version")) is not int
        or proof["evidence_version"] < 1
        or type(proof.get("handoff_revision")) is not int
        or proof["handoff_revision"] < 1
        or not isinstance(proof.get("evidence_digest"), str)
        or not _DIGEST.fullmatch(proof["evidence_digest"])
        or not isinstance(proof.get("confirmation_id"), str)
        or not proof["confirmation_id"]
    ):
        return "field_inspection_proof_invalid"
    actual, metrics = proof.get("actual"), proof.get("metrics")
    if not isinstance(actual, dict) or not isinstance(metrics, dict):
        return "field_inspection_proof_invalid"
    photo_id, photo_sha = proof.get("photo_evidence_id"), proof.get("photo_content_sha256")
    if (photo_id is None) != (photo_sha is None):
        return "field_inspection_proof_invalid"
    if photo_id is not None:
        try:
            UUID(photo_id)
        except (TypeError, ValueError, AttributeError):
            return "field_inspection_proof_invalid"
        if not isinstance(photo_sha, str) or not _DIGEST.fullmatch(photo_sha):
            return "field_inspection_proof_invalid"
    notes = actual.get("finding_notes")
    if notes is not None and not isinstance(notes, str):
        return "field_inspection_proof_invalid"
    expected_digest = hashlib.sha256(
        "|".join(
            "" if value is None else str(value) for value in (photo_id, photo_sha, notes)
        ).encode()
    ).hexdigest()
    if expected_digest != proof["evidence_digest"]:
        return "field_inspection_proof_binding_mismatch"
    identity_keys = (
        "tenant_id",
        "field_id",
        "pin_id",
        "execution_request_id",
        "decision_id",
        "execution_plan_id",
        "dispatch_authorization_id",
        "receipt_id",
        "correlation_id",
        "completed_at",
        "handoff_revision",
        "evidence_version",
        "evidence_digest",
        "photo_evidence_id",
        "photo_content_sha256",
        "inspector_id",
        "reviewer_id",
    )
    expected_actual = {key: proof.get(key) for key in identity_keys}
    expected_actual.update(
        provider="field-management-service",
        operation_type="field_inspection",
        provider_task_id=proof["task_id"],
        task_status="completed",
        finding_notes=notes,
    )
    if (
        proof.get("verification_state") != "verified_success"
        or not _same_json(actual, expected_actual)
        or not _same_json(metrics, {"inspection_approved": True})
    ):
        return "field_inspection_proof_binding_mismatch"
    try:
        fingerprint = hashlib.sha256(
            json.dumps(
                {"actual": actual, "metrics": metrics},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode()
        ).hexdigest()
    except (ValueError, TypeError):
        return "field_inspection_proof_invalid"
    if (
        proof["confirmation_id"] != "fic_" + fingerprint[:32]
        or proof.get("evidence_snapshot_id") != "inspection_" + fingerprint
        or proof.get("idempotency_key") != "inspect-outcome-" + fingerprint
    ):
        return "field_inspection_proof_binding_mismatch"
    try:
        observed = datetime.fromisoformat(proof.get("observed_at", ""))
        if observed.utcoffset() is None:
            return "field_inspection_proof_invalid"
    except (TypeError, ValueError):
        return "field_inspection_proof_invalid"
    if (
        proof.get("evidence_snapshot_id") != payload.evidence_snapshot_id
        or proof.get("idempotency_key") != payload.idempotency_key
        or not _same_json(actual, payload.actual)
        or not _same_json(metrics, payload.metrics)
    ):
        return "field_inspection_payload_mismatch"
    return None
