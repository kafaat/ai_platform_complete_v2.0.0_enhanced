"""RS-7 anti-corruption bridge to the existing task/scouting domain."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class TaskBridgeResult:
    task_ref: str
    persisted: bool
    raw: dict[str, Any]


class GroundVerificationBridge:
    def __init__(self, base_url: str | None = None, timeout: float = 10.0) -> None:
        self.base_url = (base_url or os.getenv("TASK_SERVICE_URL", "")).rstrip("/")
        self.timeout = timeout

    async def create_scouting_task(
        self,
        *,
        anomaly: dict[str, Any],
        authorization: str,
        idempotency_key: str,
    ) -> TaskBridgeResult:
        if not self.base_url:
            raise RuntimeError("task_service_not_configured")
        body = {
            "anomaly_ref": anomaly["anomaly_ref"],
            "field_id": anomaly["field_id"],
            "season_id": anomaly["season_id"],
            "geometry_ref": anomaly.get("geometry_ref"),
            "priority": anomaly.get("severity", "medium"),
            "verification_deadline": anomaly.get("verification_deadline"),
            "reason_codes": anomaly.get("reason_codes") or [],
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/tasks/scouting",
                json=body,
                headers={
                    "Authorization": authorization,
                    "Idempotency-Key": idempotency_key,
                },
            )
        if response.status_code not in {200, 201, 202}:
            raise RuntimeError(f"task_service_rejected:{response.status_code}")
        data = response.json()
        task_ref = data.get("task_ref") or data.get("task_id")
        if not task_ref:
            raise RuntimeError("task_service_missing_task_ref")
        if not str(task_ref).startswith("urn:sahool:task:"):
            task_ref = f"urn:sahool:task:{task_ref}"
        return TaskBridgeResult(task_ref=str(task_ref), persisted=True, raw=data)
