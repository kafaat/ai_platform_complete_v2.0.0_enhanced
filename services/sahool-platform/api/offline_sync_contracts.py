"""Offline sync runtime contracts for mobile/web field operations.

This module is intentionally pure Python: no DB, no network, no FastAPI. It defines
server-authoritative contracts used by ``api.routers.sync`` so mobile retries after
weak connectivity keep stable operation IDs, preserve field-version conflict guards,
and expose a machine-readable manifest to clients.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

try:  # loaded inside sahool-platform package at runtime/tests
    from core.offline_first import OperationKind
except Exception:  # pragma: no cover - static import fallback
    OperationKind = None  # type: ignore[assignment]

FIELD_UPDATE_KIND = "field.update"

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass(frozen=True)
class SyncContractIssue:
    field: str
    code: str
    message: str
    severity: str = "error"


def _known_operation_kinds() -> set[str]:
    values = {FIELD_UPDATE_KIND}
    if OperationKind is not None:
        values.update(k.value for k in OperationKind)  # type: ignore[union-attr]
    return values


def is_uuid_like(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        uuid.UUID(value.strip())
        return True
    except ValueError:
        return False


def _coerce_client_operation_id(raw: dict[str, Any]) -> str | None:
    """Return a stable client operation id if supplied.

    Mobile versions historically used either ``op_id`` or ``operation_id``. We accept
    both but never invent here; the existing queue can still generate an ID for legacy
    clients. When supplied, the caller must preserve it end-to-end for DB idempotency.
    """

    candidate = raw.get("op_id") or raw.get("operation_id") or raw.get("idempotency_key")
    if candidate is None:
        return None
    candidate_s = str(candidate).strip()
    if not is_uuid_like(candidate_s):
        raise ValueError("offline sync operation id must be a UUID")
    return str(uuid.UUID(candidate_s))


def normalize_offline_operation(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize one offline operation without applying it.

    Compatibility policy:
    - ``op_id``/``operation_id`` are optional for legacy clients.
    - if present, the UUID is normalized and must be preserved by the sync router.
    - ``kind`` defaults to ``observation_create`` as the old endpoint did.
    - payload defaults to ``{}`` but must be a JSON object when present.
    - ``field.update`` receives explicit conflict metadata for mobile UX.
    """

    if not isinstance(raw, dict):
        raise ValueError("offline sync operation must be an object")

    kind = str(raw.get("kind", "observation_create")).strip()
    if kind not in _known_operation_kinds():
        valid = ", ".join(sorted(_known_operation_kinds()))
        raise ValueError(f"unknown offline sync operation kind {kind!r}; allowed: {valid}")

    payload = raw.get("payload", {})
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("offline sync operation payload must be an object")

    client_op_id = _coerce_client_operation_id(raw)
    normalized = {
        "op_id": client_op_id,
        "kind": kind,
        "payload": payload,
        "client_seq": raw.get("client_seq"),
        "device_id": raw.get("device_id"),
        "created_at": raw.get("created_at"),
        "requires_conflict_resolution": False,
        "conflict_policy": "ledger_only",
    }

    if kind == FIELD_UPDATE_KIND:
        normalized["conflict_policy"] = "optimistic_row_version"
        normalized["requires_conflict_resolution"] = True
        # Do not hard-fail legacy writes that lack base_version; the lower DB path still
        # applies server-side ownership/RLS. Surface the gap so modern clients can show a
        # merge UI instead of overwriting blindly.
        normalized["has_base_version"] = payload.get("base_version") is not None
        normalized["field_id"] = payload.get("field_id")
    return normalized


def validate_sync_batch(tenant_id: str, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id is required")
    if not isinstance(operations, list):
        raise ValueError("operations must be a list")
    return [normalize_offline_operation(op) for op in operations]


def build_sync_manifest() -> dict[str, Any]:
    """Machine-readable contract consumed by mobile/web sync clients."""

    now = datetime.now(UTC).isoformat()
    return {
        "schema_version": "2026-06-26.phase11-mobile-sync-runtime",
        "generated_at": now,
        "stable_operation_id": {
            "accepted_fields": ["op_id", "operation_id", "idempotency_key"],
            "format": "uuid",
            "required_for_new_clients": True,
            "legacy_clients_without_id": "server_generates_id_but_cross-request_idempotency_is_limited",
        },
        "supported_operation_kinds": sorted(_known_operation_kinds()),
        "dispatch": {
            FIELD_UPDATE_KIND: {
                "mode": "apply",
                "conflict_policy": "optimistic_row_version",
                "required_payload": ["field_id"],
                "recommended_payload": ["base_version"],
                "conflict_status": "conflict",
            },
            "default": {
                "mode": "ledger_only",
                "conflict_policy": "none",
            },
        },
        "status_endpoint": "/api/v1/sync/status",
        "batch_endpoint": "/api/v1/sync",
        "delta_sync": {
            "feature_flag": "FEATURE_DELTA_SYNC",
            "cursor_query_parameter": "since",
        },
    }


def summarize_sync_status(
    *, queued: int, queue_size: int, durable_pending: int | None = None
) -> dict[str, Any]:
    """Return a stable sync status shape for UI/readiness without exposing internals."""

    return {
        "status": "ok",
        "queue": {
            "queued": int(queued),
            "size": int(queue_size),
            "durable_pending": durable_pending,
        },
        "healthy_for_sync": queued < 1000 and (durable_pending is None or durable_pending < 5000),
        "reason_ar": "طابور المزامنة جاهز"
        if queued < 1000
        else "طابور المزامنة مرتفع ويحتاج تفريغاً",
    }
