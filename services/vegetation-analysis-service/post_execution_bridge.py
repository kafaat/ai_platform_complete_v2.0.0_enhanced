"""RS-10 bridge: schedule post-execution observations and verify attributable outcomes.

The bridge never owns execution or canonical outcomes. It requests follow-up imagery
from raster-service and delegates outcome verification/learning attribution to the
existing decision-service SoR. All writes fail closed when an upstream is unavailable.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx


class PostExecutionBridge:
    def __init__(self) -> None:
        self.raster_url = os.getenv(
            "RASTER_SERVICE_URL", "http://sahool-raster-service:8001"
        ).rstrip("/")
        self.decision_url = os.getenv(
            "DECISION_SERVICE_URL", "http://sahool-decision-service:8160"
        ).rstrip("/")
        self.timeout = float(os.getenv("RS10_BRIDGE_TIMEOUT_S", "8"))

    @staticmethod
    def _idempotency(*parts: str) -> str:
        raw = "|".join(parts).encode("utf-8")
        return "idmp_rs10_" + hashlib.sha256(raw).hexdigest()

    async def schedule_follow_up(
        self,
        *,
        field_id: str,
        season_id: str,
        execution_request_id: str,
        authorization: str,
        tenant_id: str,
        days_after: int,
        indicators: list[str],
    ) -> dict[str, Any]:
        target_date = (datetime.now(UTC) + timedelta(days=days_after)).date().isoformat()
        body = {
            "season_id": season_id,
            "platforms": ["sentinel-2", "sentinel-1"],
            "cloud_max": 30,
            "processing_options": {
                "indicators": indicators,
                "purpose": "post_execution_verification",
                "target_date": target_date,
                "execution_request_id": execution_request_id,
            },
        }
        headers = {
            "Authorization": authorization,
            "X-Tenant-Id": tenant_id,
            "Idempotency-Key": self._idempotency(
                tenant_id, field_id, execution_request_id, target_date
            ),
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.raster_url}/v1/fields/{field_id}/imagery-ingestion-requests",
                json=body,
                headers=headers,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"raster_follow_up_rejected:{response.status_code}")
        return {
            "target_date": target_date,
            "request": response.json(),
            "idempotency_key": headers["Idempotency-Key"],
        }

    async def verify_outcome(
        self,
        *,
        execution_request_id: str,
        authorization: str,
        tenant_id: str,
        verified_by: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        headers = {
            "Authorization": authorization,
            "X-Tenant-Id": tenant_id,
            "X-Verified-By": verified_by,
            "Idempotency-Key": str(
                payload.get("idempotency_key")
                or self._idempotency(tenant_id, execution_request_id, "verify")
            ),
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.decision_url}/v1/execution-requests/{execution_request_id}/verify-outcome",
                json=payload,
                headers=headers,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"outcome_verification_rejected:{response.status_code}")
        return response.json()

    async def attribute_learning(
        self,
        *,
        outcome_id: str,
        authorization: str,
        tenant_id: str,
        attributed_by: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        headers = {
            "Authorization": authorization,
            "X-Tenant-Id": tenant_id,
            "X-Attributed-By": attributed_by,
            "Idempotency-Key": str(
                payload.get("idempotency_key")
                or self._idempotency(tenant_id, outcome_id, "attribute")
            ),
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.decision_url}/v1/outcomes/{outcome_id}/learning-attribution",
                json=payload,
                headers=headers,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"learning_attribution_rejected:{response.status_code}")
        return response.json()
