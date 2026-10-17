"""RS-10 bridge: schedule post-execution observations and verify attributable outcomes.

The bridge never owns execution or canonical outcomes. It requests follow-up imagery
from raster-service and delegates outcome verification/learning attribution to the
existing decision-service SoR. All writes fail closed when an upstream is unavailable.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any
from urllib.parse import quote

import httpx

from shared.contracts.imagery_followup import ImageryFollowUpRequest, request_identity


class PostExecutionBridge:
    def __init__(self) -> None:
        self.raster_url = os.getenv(
            "RASTER_SERVICE_URL", "http://sahool-raster-service:8001"
        ).rstrip("/")
        # Human outcome/learning writes use the platform's existing RBAC boundary.
        # It derives tenant and actor from the JWT before calling decision-service.
        self.platform_url = os.getenv("PLATFORM_API_URL", "http://sahool-platform:8000").rstrip("/")
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
        window_days: int = 7,
    ) -> dict[str, Any]:
        body = ImageryFollowUpRequest(
            season_id=season_id,
            execution_request_id=execution_request_id,
            days_after=days_after,
            window_days=window_days,
            indicators=indicators,
        ).model_dump()
        headers = {
            "Authorization": authorization,
            "X-Tenant-Id": tenant_id,
            "Idempotency-Key": request_identity(tenant_id, field_id, execution_request_id),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                response = await client.post(
                    f"{self.raster_url}/v1/fields/{quote(field_id, safe='')}/imagery-ingestion-requests",
                    json=body,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise RuntimeError("raster_follow_up_unavailable") from exc
        if response.status_code >= 400:
            raise RuntimeError(f"raster_follow_up_rejected:{response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError("raster_follow_up_contract_mismatch") from exc
        if (
            response.status_code != 202 or not isinstance(data, dict)
            or data.get("request_id") != headers["Idempotency-Key"]
            or not isinstance(data.get("due_at"), str)
            or data.get("time_basis") != "delivery_receipt_received_at"
        ):
            raise RuntimeError("raster_follow_up_contract_mismatch")
        return {
            "target_date": data["due_at"][:10],
            "time_basis": data["time_basis"],
            "request": data,
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
        # verified_by remains a compatibility argument; only the session owner
        # may resolve the actor or grant DECISION_EXECUTE.
        headers = {
            "Authorization": authorization,
            "Idempotency-Key": str(
                payload.get("idempotency_key")
                or self._idempotency(tenant_id, execution_request_id, "verify")
            ),
        }
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.post(
                f"{self.platform_url}/api/v1/execution-requests/{execution_request_id}/verify-outcome",
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
        # The platform resolves the actor and DECISION_LEARNING_ATTRIBUTE.
        # Never forward the caller-supplied attributed_by as trusted identity.
        headers = {
            "Authorization": authorization,
            "Idempotency-Key": str(
                payload.get("idempotency_key")
                or self._idempotency(tenant_id, outcome_id, "attribute")
            ),
        }
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.post(
                f"{self.platform_url}/api/v1/outcomes/{outcome_id}/learning-attribution",
                json=payload,
                headers=headers,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"learning_attribution_rejected:{response.status_code}")
        return response.json()
