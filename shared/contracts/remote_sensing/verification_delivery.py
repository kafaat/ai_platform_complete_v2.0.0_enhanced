"""Canonical bytes for the existing seven-field verification completion body.

This is a transport helper, not a new evidence or agronomic validation contract.
Callers still validate with the receiver's VerificationCompletion model. Array
order is preserved, expected_version participates in the digest, and equivalent
timezone offsets identify the same instant. No float/string coercion is applied.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

_FIELDS = frozenset(
    {
        "expected_version",
        "task_ref",
        "verification_result",
        "evidence_refs",
        "evidence",
        "reason_codes",
        "completed_at",
    }
)


_TRUE = frozenset({"1", "true", "yes", "on"})


def flag_enabled(raw: str | None) -> bool:
    """The one reading of the bridge's switches, on the sender and the receiver alike.

    Callers pass ``os.getenv("<NAME>", "0")`` with the literal name, so env-closure guards
    (tests_v9/test_helm_network_policy_egress.py) still see which settings a service reads.
    """
    return str(raw or "").strip().lower() in _TRUE


def _utc_timestamp(value: Any) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("verification_timestamp_requires_timezone")
    return value.astimezone(UTC).isoformat()


def canonical_completion_payload(body: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-compatible body with its defaults and timestamps normalized.

    The input is the wire mapping, normally model_dump(mode='json'). Unknown fields
    are refused; this helper never silently drops an unsupported binding.
    """
    payload = dict(body)
    for name in ("evidence_refs", "evidence", "reason_codes"):
        payload.setdefault(name, [])
        if not isinstance(payload[name], list):
            raise ValueError("verification_array_required")
    if payload.keys() != _FIELDS:
        raise ValueError("verification_completion_fields_invalid")
    payload["completed_at"] = _utc_timestamp(payload["completed_at"])
    evidence = []
    for entry in payload["evidence"]:
        if not isinstance(entry, Mapping):
            raise ValueError("verification_evidence_mapping_required")
        item = dict(entry)
        # Match the existing EvidenceRefV1 wire defaults on both sides, even
        # when a sender serialized with exclude_none=True. This does not grant
        # eligibility: the receiver still validates the original evidence DTO.
        for name in ("quality_grade", "valid_until", "geometry_ref"):
            item.setdefault(name, None)
        item["captured_at"] = _utc_timestamp(item.get("captured_at"))
        if item.get("valid_until") is not None:
            item["valid_until"] = _utc_timestamp(item["valid_until"])
        evidence.append(item)
    payload["evidence"] = evidence
    return payload


def canonical_completion_digest(body: Mapping[str, Any]) -> str:
    """SHA-256 of the normalized body; includes the original expected version."""
    raw = json.dumps(
        canonical_completion_payload(body),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verification_request_binding(idempotency_key: str, request_digest: str) -> str:
    """Suffix for signed X-Request-Id: UUIDhex + '.' + this digest.

    Binding both the operation key and the completion digest prevents a captured
    tenant assertion from being reused with another body or delivery identity.
    """
    return hashlib.sha256(f"{idempotency_key}\n{request_digest}".encode()).hexdigest()
