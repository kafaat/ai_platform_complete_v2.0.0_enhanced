"""Request-bound S2S client for the vegetation owner's verification interface."""

from __future__ import annotations

import os
import re
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx

from shared.contracts.remote_sensing.verification_delivery import (
    canonical_completion_digest,
    canonical_completion_payload,
    verification_request_binding,
)
from shared.security.service_tenant_assertion import TenantAssertionError, create_tenant_assertion

CALLER = "field-management-service"

# Refusals the receiver (routers/verification.py) gives before it reads or writes the anomaly:
# its switch is off, or the two services' credentials disagree. The request was not applied
# and repeating it cannot succeed until an operator fixes the configuration.
CONFIGURATION_REFUSALS = frozenset(
    {
        (404, "verification_bridge_disabled"),
        (503, "verification_service_credentials_unconfigured"),
        (503, "verification_service_token_not_dedicated"),
        (403, "invalid_task_service_token"),
        (403, "verification_caller_scope_invalid"),
        (403, "invalid_verification_tenant_assertion"),
    }
)
# Refusals of this request itself: the owner will never apply it, so retrying is pointless.
# Every 409 from the receiver is an anomaly-store InvalidTransition (version conflict, result
# already recorded, idempotency key reused with another body); 422 is an invalid request.
CONTENT_REJECTIONS = frozenset(
    {
        (403, "verification_request_body_binding_mismatch"),
        (403, "verification_evidence_tenant_mismatch"),
        (404, "anomaly not found"),
    }
)


def _sanitize(detail: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", detail)[:80]


class VerificationRemoteError(RuntimeError):
    """The outcome at the owner is unknown: the request may or may not have been applied."""

    def __init__(self, reason: str, *, status: int | None = None, detail=None):
        super().__init__(reason)
        self.status = status
        self.detail = detail


class VerificationRemoteRefused(VerificationRemoteError):
    """The receiver identified itself and refused for a configuration reason; nothing applied."""


class VerificationRemoteRejected(VerificationRemoteError):
    """The receiver definitively refused this request; it will never be applied."""


def classify_refusal(status: int, detail) -> type[VerificationRemoteError]:
    if isinstance(detail, list) and detail and status == 422:
        # FastAPI's own validation reply: the receiver refused the request body.
        return VerificationRemoteRejected
    if not isinstance(detail, str) or not detail:
        # A body without the receiver's detail (a proxy's 502/503/422, an HTML error page)
        # says nothing about the owner, so the outcome stays unknown.
        return VerificationRemoteError
    if (status, detail) in CONFIGURATION_REFUSALS:
        return VerificationRemoteRefused
    if status in {409, 422} or (status, detail) in CONTENT_REJECTIONS:
        return VerificationRemoteRejected
    return VerificationRemoteError


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
        key_id = os.getenv("VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY_ID", "current")
        parts = urlsplit(url)
        # Plain http is accepted on purpose: the receiver lives on the private service network,
        # like every other service-to-service call in compose, and the signed assertion binds
        # method, path and request id. TLS would add confidentiality for the token on that
        # network; it is a deployment choice, not something this client can verify.
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
        # The receiver looks the key id up verbatim, and HTTP headers carry ASCII without control
        # characters. A padded, non-ASCII or control-character id would be claimed and then fail
        # (or be signed as a different, stripped id), so it is refused here, before any claim.
        if (
            key_id != key_id.strip()
            or not key_id.isascii()
            or any(ord(char) < 32 or ord(char) == 127 for char in key_id)
        ):
            raise VerificationRemoteError("verification_transport_unconfigured")
        try:
            # The assertion's own rule decides whether this key id is signable (not empty, no
            # ':' or line break), so a malformed id is refused here, before any claim.
            create_tenant_assertion(
                key, CALLER, "probe", key_id=key_id, method="GET", path="/", request_id="probe"
            )
        except TenantAssertionError as exc:
            raise VerificationRemoteError("verification_transport_unconfigured") from exc
        return url, token, key, key_id

    def configured(self) -> bool:
        """True when a request could be signed; checked before a delivery is claimed."""
        try:
            self._configuration()
        except VerificationRemoteError:
            return False
        return True

    async def _request(self, method, tenant, anomaly_ref, suffix, *, body=None, key=None):
        base, token, assertion_key, key_id = self._configuration()
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
        }
        try:
            headers["X-Tenant-Assertion"] = create_tenant_assertion(
                assertion_key,
                CALLER,
                str(tenant),
                key_id=key_id,
                method=method,
                path=path,
                request_id=request_id,
            )
            for value in headers.values():
                value.encode("ascii")
        except (TenantAssertionError, UnicodeEncodeError) as exc:
            # Nothing was sent; the dispatcher settles the claimed row instead of stranding it.
            raise VerificationRemoteRefused("verification_assertion_unsignable") from exc
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
            try:
                detail = response.json().get("detail")
            except (ValueError, AttributeError):
                detail = None
            kind = classify_refusal(response.status_code, detail)
            reason = f"verification_remote_status:{response.status_code}"
            if isinstance(detail, str) and detail:
                # Visible to an operator in last_error. Only the receiver's named codes appear
                # as sent; anything else (an unknown reply, a 409/422 store message) is reduced to
                # a short, plain token so a remote reply cannot inject arbitrary text there.
                named = (
                    response.status_code,
                    detail,
                ) in CONFIGURATION_REFUSALS | CONTENT_REJECTIONS
                shown = detail if named else _sanitize(detail)
                reason += f":{shown}"
            raise kind(reason, status=response.status_code, detail=detail)
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
