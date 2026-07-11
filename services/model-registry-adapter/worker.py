"""Single-iteration worker primitives for activation and rollback commands.
Network orchestration is explicit so supervisors can retry without hiding duplicate execution.
"""

from __future__ import annotations

import json
import os
import secrets
import urllib.request
from typing import Any

from adapter import HttpRegistry, RegistryError, validate_runtime

BASE = os.getenv("DECISION_SERVICE_URL", "http://decision-service:8090").rstrip("/")
TOKEN = os.getenv("DECISION_SERVICE_TOKEN", "")
ADAPTER_ID = os.getenv("REGISTRY_ADAPTER_ID", "")


def _post(path: str, payload: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    headers = {"Content-Type": "application/json", "X-Tenant-Id": tenant_id}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def execute_activation(command: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    validate_runtime()
    if not ADAPTER_ID:
        raise RegistryError("REGISTRY_ADAPTER_ID is required")
    delivery_token = secrets.token_urlsafe(32)
    cid = command["activation_command_id"]
    _post(
        f"/v1/learning/activation-commands/{cid}/claim",
        {"adapter_id": ADAPTER_ID, "delivery_token": delivery_token},
        tenant_id,
    )
    registry = HttpRegistry()
    try:
        state = registry.compare_and_swap(
            model_id=command["model_id"],
            environment=command["target_environment"],
            alias=command["registry_alias"],
            expected_digest=command["previous_artifact_digest"],
            artifact_uri=command["candidate_artifact_uri"],
            artifact_digest=command["candidate_artifact_digest"],
        )
        return _post(
            f"/v1/learning/activation-commands/{cid}/receipt",
            {
                "adapter_id": ADAPTER_ID,
                "delivery_token": delivery_token,
                "receipt_state": "activated",
                "active_artifact_uri": state.artifact_uri,
                "active_artifact_digest": state.artifact_digest,
                "registry_version": state.version,
            },
            tenant_id,
        )
    except Exception as exc:
        _post(
            f"/v1/learning/activation-commands/{cid}/receipt",
            {
                "adapter_id": ADAPTER_ID,
                "delivery_token": delivery_token,
                "receipt_state": "failed",
                "failure_reason": str(exc)[:500],
            },
            tenant_id,
        )
        raise


def execute_rollback(command: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    validate_runtime()
    if not ADAPTER_ID:
        raise RegistryError("REGISTRY_ADAPTER_ID is required")
    delivery_token = secrets.token_urlsafe(32)
    cid = command["rollback_command_id"]
    _post(
        f"/v1/learning/rollback-commands/{cid}/claim",
        {"adapter_id": ADAPTER_ID, "delivery_token": delivery_token},
        tenant_id,
    )
    registry = HttpRegistry()
    try:
        state = registry.compare_and_swap(
            model_id=command["model_id"],
            environment=command["target_environment"],
            alias=command["registry_alias"],
            expected_digest=command["replace_artifact_digest"],
            artifact_uri=command["restore_artifact_uri"],
            artifact_digest=command["restore_artifact_digest"],
        )
        return _post(
            f"/v1/learning/rollback-commands/{cid}/receipt",
            {
                "adapter_id": ADAPTER_ID,
                "delivery_token": delivery_token,
                "receipt_state": "rolled_back",
                "active_artifact_uri": state.artifact_uri,
                "active_artifact_digest": state.artifact_digest,
                "registry_version": state.version,
            },
            tenant_id,
        )
    except Exception as exc:
        _post(
            f"/v1/learning/rollback-commands/{cid}/receipt",
            {
                "adapter_id": ADAPTER_ID,
                "delivery_token": delivery_token,
                "receipt_state": "rollback_failed",
                "failure_reason": str(exc)[:500],
            },
            tenant_id,
        )
        raise
