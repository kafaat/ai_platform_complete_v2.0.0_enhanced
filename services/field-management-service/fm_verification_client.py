"""Request-bound S2S client for the vegetation owner's verification interface."""

from __future__ import annotations

import os
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx

from shared.contracts.remote_sensing.verification_delivery import (
    canonical_completion_digest,
    canonical_completion_payload,
    verification_request_binding,
)
from shared.security.service_tenant_assertion import create_tenant_assertion

CALLER = "field-management-service"


class VerificationRemoteError(RuntimeError):
    pass


class VegetationVerificationClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        # Injecting a transport is a test seam; the URL always comes from the
        # service's configuration, never from a user's request or an evidence URL.
        self.client = client

    @staticmethod
    def _configuration():
        url = os.getenv("VEGETATION_VERIFICATION_URL", "").rstrip("/")
        token = os.getenv("VEGETATION_VERIFICATION_SERVICE_TOKEN", "")
        key = os.getenv("VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY", "")
        parts = urlsplit(url)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.netloc
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.path not in {"", "/"}
            or not token
            or len(key) < 32
        ):
            raise VerificationRemoteError("verification_transport_unconfigured")
        return url, token, key

    async def _request(self, method, tenant, anomaly_ref, suffix, *, body=None, key=None):
        base, token, assertion_key = self._configuration()
        path = f"/internal/anomalies/{quote(str(anomaly_ref), safe='')}/{suffix}"
        request_id = uuid4().hex
        if body is not None:
            body = canonical_completion_payload(body)
            request_id += "." + verification_request_binding(key, canonical_completion_digest(body))
        headers = {
            "X-Task-Service-Token": token,
            "X-Service-Name": CALLER,
            "X-Tenant-Id": str(tenant),
            "X-Request-Id": request_id,
            "X-Tenant-Assertion": create_tenant_assertion(
                assertion_key,
                CALLER,
                str(tenant),
                key_id=os.getenv("VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY_ID", "current"),
                method=method,
                path=path,
                request_id=request_id,
            ),
        }
        if key:
            headers["Idempotency-Key"] = key

        async def send(client):
            return await client.request(
                method, base + path, headers=headers, json=body, follow_redirects=False
            )

        try:
            if self.client is not None:
                response = await send(self.client)
            else:
                async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                    response = await send(client)
        except httpx.HTTPError as exc:
            raise VerificationRemoteError("verification_delivery_unknown") from exc
        if response.status_code not in {200, 201}:
            raise VerificationRemoteError(f"verification_remote_status:{response.status_code}")
        try:
            result = response.json()
        except ValueError as exc:
            raise VerificationRemoteError("verification_reply_unreadable") from exc
        if not isinstance(result, dict) or result.get("persisted") is not True:
            raise VerificationRemoteError("verification_persistence_unconfirmed")
        return result

    async def context(self, tenant: str, anomaly_ref: str) -> dict:
        return await self._request("GET", tenant, anomaly_ref, "verification-context")

    async def complete(self, tenant: str, anomaly_ref: str, body: dict, key: str) -> dict:
        return await self._request(
            "POST", tenant, anomaly_ref, "verification-results", body=body, key=key
        )
