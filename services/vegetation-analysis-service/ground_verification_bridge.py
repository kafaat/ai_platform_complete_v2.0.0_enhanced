"""RS-7 anti-corruption bridge to the owner of field tasks (field-management-service).

W1-20 (findings remote-7 / scout-5): the bridge used to POST ``/v1/tasks/scouting``, which no
service served, so every ground-verification request failed. field-management-service, the
owner of ``field_tasks``, now serves ``POST /internal/field-tasks/scouting`` (v282). It is a
service-to-service route, called the way this service already reads ``/internal/fields``
(vegetation_runtime.py): the shared service token, this service's name, the verified tenant and
a short-lived tenant assertion bound to the method, path and request id. The user's bearer token
is not forwarded: the owner never decodes a user JWT.

Fail closed: no URL, no token or no assertion key raises before any request; any reply that is
not a stored task (``persisted: true`` and a task id) raises too, so the anomaly never moves to
``verification_requested`` without a real task.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from shared.security.service_tenant_assertion import (
    TenantAssertionError,
    create_tenant_assertion,
)

SCOUTING_TASKS_PATH = "/internal/field-tasks/scouting"
CALLER = "vegetation-analysis-service"


@dataclass(frozen=True)
class TaskBridgeResult:
    task_ref: str
    persisted: bool
    raw: dict[str, Any]


class GroundVerificationBridge:
    def __init__(self, base_url: str | None = None, timeout: float = 10.0) -> None:
        self._base_url = base_url
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        # Read at call time: the compose default names field-management-service.
        return (self._base_url or os.getenv("TASK_SERVICE_URL", "")).rstrip("/")

    def _headers(self, tenant_id: str, idempotency_key: str) -> dict[str, str]:
        token = os.getenv("SAHOOL_AGENT_TOKEN", "")
        key = os.getenv("FIELD_SERVICE_TENANT_ASSERTION_KEY", "")
        if not token:
            raise RuntimeError("task_service_token_not_configured")
        if not key:
            raise RuntimeError("task_service_tenant_assertion_unavailable")
        request_id = str(uuid.uuid4())
        try:
            assertion = create_tenant_assertion(
                key,
                CALLER,
                str(tenant_id),
                key_id=os.getenv("FIELD_SERVICE_TENANT_ASSERTION_KEY_ID", "current"),
                method="POST",
                path=SCOUTING_TASKS_PATH,
                request_id=request_id,
            )
        except TenantAssertionError as exc:
            raise RuntimeError("task_service_tenant_assertion_unavailable") from exc
        return {
            "X-Agent-Token": token,
            "X-Service-Name": CALLER,
            "X-Tenant-Id": str(tenant_id),
            "X-Request-Id": request_id,
            "X-Tenant-Assertion": assertion,
            "Idempotency-Key": idempotency_key,
        }

    async def create_scouting_task(
        self,
        *,
        anomaly: dict[str, Any],
        tenant_id: str,
        idempotency_key: str,
    ) -> TaskBridgeResult:
        base_url = self.base_url
        if not base_url:
            raise RuntimeError("task_service_not_configured")
        if not tenant_id or str(anomaly.get("tenant_id") or tenant_id) != str(tenant_id):
            raise RuntimeError("task_service_tenant_mismatch")
        headers = self._headers(tenant_id, idempotency_key)
        body = {
            "anomaly_ref": anomaly["anomaly_ref"],
            "field_id": anomaly["field_id"],
            "season_id": anomaly["season_id"],
            "geometry_ref": anomaly.get("geometry_ref"),
            "priority": anomaly.get("severity", "medium"),
            "verification_deadline": anomaly.get("verification_deadline"),
            "reason_codes": anomaly.get("reason_codes") or [],
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                response = await client.post(
                    f"{base_url}{SCOUTING_TASKS_PATH}", json=body, headers=headers
                )
        except httpx.HTTPError as exc:
            raise RuntimeError("task_service_unavailable") from exc
        if response.status_code not in {200, 201, 202}:
            raise RuntimeError(f"task_service_rejected:{response.status_code}")
        data = response.json()
        if data.get("persisted") is not True:
            raise RuntimeError("task_service_persistence_unconfirmed")
        task_ref = data.get("task_ref") or data.get("task_id")
        if not task_ref:
            raise RuntimeError("task_service_missing_task_ref")
        if not str(task_ref).startswith("urn:sahool:task:"):
            task_ref = f"urn:sahool:task:{task_ref}"
        return TaskBridgeResult(task_ref=str(task_ref), persisted=True, raw=data)
