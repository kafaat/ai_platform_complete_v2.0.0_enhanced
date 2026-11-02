"""Single-iteration worker primitives for activation and rollback commands.
Network orchestration is explicit so supervisors can retry without hiding duplicate execution.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import urllib.request
from typing import Any

from adapter import HttpRegistry, RegistryError, RegistryState, validate_runtime

LOG = logging.getLogger("model-lifecycle-worker")

BASE = os.getenv("DECISION_SERVICE_URL", "http://sahool-decision-service:8160").rstrip("/")
TOKEN = os.getenv("DECISION_SERVICE_TOKEN", "")
ADAPTER_ID = os.getenv("REGISTRY_ADAPTER_ID", "")


def _post(
    path: str,
    payload: dict[str, Any],
    tenant_id: str,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-Id": tenant_id,
        **(extra_headers or {}),
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def delivery_token(kind: str, command_id: str, tenant_id: str) -> str:
    """Deterministic, secret-keyed claim proof for one (adapter, tenant, command).

    R3: a random token per attempt meant the claim recorded by a worker that crashed before its
    receipt could never be replayed by its successor (same REGISTRY_ADAPTER_ID): decision-service
    stores only the token hash (append-only claim row) and rejects any other token as
    "claimed_by_another_adapter" forever. An HMAC over the command identity under a secret the
    adapter deployment already holds lets a restarted/replica worker re-present the SAME proof, so
    the claim replays idempotently and the command can still be completed.
    رمزٌ حتميّ مُفتاحيّ: خليفة العامل المنهار يُعيد المطالبة نفسها بدل أن تعلق إلى الأبد.
    """
    secret = os.getenv("REGISTRY_DELIVERY_TOKEN_SECRET", "").strip() or os.getenv(
        "DECISION_SERVICE_TOKEN", ""
    )
    if not secret:
        if os.getenv("SAHOOL_ENV", "").lower() == "production":
            raise RegistryError(
                "REGISTRY_DELIVERY_TOKEN_SECRET (or DECISION_SERVICE_TOKEN) is required in production"
            )
        secret = f"sahool-dev-delivery-token:{ADAPTER_ID}"  # dev only: no auth configured anyway
    message = f"registry-delivery:v1:{kind}:{tenant_id}:{command_id}:{ADAPTER_ID}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def _swap_or_confirm(
    registry: HttpRegistry,
    *,
    model_id: str,
    environment: str,
    alias: str,
    expected_digest: str,
    artifact_uri: str,
    artifact_digest: str,
) -> RegistryState:
    """CAS, but a retry after a crash is idempotent: if the alias ALREADY points at the requested
    digest (our pre-crash swap, or a same-identity replica's), report that live state instead of a
    false "failed" receipt. Any other CAS failure is re-raised unchanged.
    إعادة المحاولة بعد الانهيار: إن كان التبديل قد تمّ فعلاً نُبلغ الحالة الحيّة لا «فشل» كاذباً.
    """
    try:
        return registry.compare_and_swap(
            model_id=model_id,
            environment=environment,
            alias=alias,
            expected_digest=expected_digest,
            artifact_uri=artifact_uri,
            artifact_digest=artifact_digest,
        )
    except Exception as cas_error:
        try:
            current = registry.get(model_id, environment, alias)
        except Exception:
            raise cas_error from None
        if str(current.artifact_digest).lower() == artifact_digest.lower():
            LOG.warning(
                "CAS for %s/%s/%s refused but alias already at target digest — idempotent retry",
                model_id,
                environment,
                alias,
            )
            return current
        raise


def execute_activation(command: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    validate_runtime()
    if not ADAPTER_ID:
        raise RegistryError("REGISTRY_ADAPTER_ID is required")
    cid = command["activation_command_id"]
    token = delivery_token("activation", cid, tenant_id)
    _post(
        f"/v1/learning/activation-commands/{cid}/claim",
        {"adapter_id": ADAPTER_ID, "delivery_token": token},
        tenant_id,
    )
    registry = HttpRegistry()
    try:
        state = _swap_or_confirm(
            registry,
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
                "delivery_token": token,
                "receipt_state": "activated",
                "active_artifact_uri": state.artifact_uri,
                "active_artifact_digest": state.artifact_digest,
                "registry_version": state.version,
                "idempotency_key": f"activation-receipt:{cid}",
            },
            tenant_id,
            {"X-Recorded-By": ADAPTER_ID},
        )
    except Exception as exc:
        _post(
            f"/v1/learning/activation-commands/{cid}/receipt",
            {
                "adapter_id": ADAPTER_ID,
                "delivery_token": token,
                "receipt_state": "failed",
                "failure_reason": str(exc)[:500],
                "idempotency_key": f"activation-receipt:{cid}",
            },
            tenant_id,
            {"X-Recorded-By": ADAPTER_ID},
        )
        raise


def execute_rollback(command: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    validate_runtime()
    if not ADAPTER_ID:
        raise RegistryError("REGISTRY_ADAPTER_ID is required")
    cid = command["rollback_command_id"]
    token = delivery_token("rollback", cid, tenant_id)
    _post(
        f"/v1/learning/rollback-commands/{cid}/claim",
        {"adapter_id": ADAPTER_ID, "delivery_token": token},
        tenant_id,
    )
    registry = HttpRegistry()
    try:
        state = _swap_or_confirm(
            registry,
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
                "delivery_token": token,
                "receipt_state": "rolled_back",
                "active_artifact_uri": state.artifact_uri,
                "active_artifact_digest": state.artifact_digest,
                "registry_version": state.version,
                "idempotency_key": f"rollback-receipt:{cid}",
            },
            tenant_id,
            {"X-Recorded-By": ADAPTER_ID},
        )
    except Exception as exc:
        _post(
            f"/v1/learning/rollback-commands/{cid}/receipt",
            {
                "adapter_id": ADAPTER_ID,
                "delivery_token": token,
                "receipt_state": "rollback_failed",
                "failure_reason": str(exc)[:500],
                "idempotency_key": f"rollback-receipt:{cid}",
            },
            tenant_id,
            {"X-Recorded-By": ADAPTER_ID},
        )
        raise
