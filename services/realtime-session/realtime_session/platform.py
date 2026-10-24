"""Read identity and field authorization from the canonical SAHOOL platform.

The caller owns the HTTP client and must pass the bearer used to obtain the
principal to ``authorize_field`` in the same request. No caller-supplied tenant
header, local token decode, policy cache, or fallback authority is used here.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
from urllib.parse import quote, urlsplit

import httpx

from .contracts import Principal, SessionError

_MAX_RESPONSE_BYTES = 64 * 1024
_TIMEOUT_SECONDS = 3.0
_TOTAL_TIMEOUT_SECONDS = 4.0


def _base_url(value: str) -> str:
    """Reject ambiguous origins and plaintext external destinations."""
    try:
        if not isinstance(value, str) or "\\" in value or any(ord(c) < 33 for c in value):
            raise ValueError
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or "?" in value
            or "#" in value
            or (parsed.port is not None and not 1 <= parsed.port <= 65535)
        ):
            raise ValueError
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == "localhost"
        internal = host == "sahool-platform" or host.endswith(".railway.internal")
        if parsed.scheme == "http" and not (loopback or internal):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise SessionError(503, "platform_url_invalid") from None
    return value.rstrip("/")


def _identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= 256
        and not any(ord(c) < 32 or ord(c) == 127 for c in value)
    )


class PlatformAuthority:
    def __init__(self, base_url: str, client: httpx.AsyncClient):
        self._base_url = _base_url(base_url)
        self._client = client

    async def _get(self, path: str, bearer: str) -> dict:
        if (
            not isinstance(bearer, str)
            or not bearer.strip()
            or len(bearer) > 16384
            or any(ord(c) < 32 or ord(c) == 127 for c in bearer)
        ):
            raise SessionError(401, "authentication_required")
        try:
            async with asyncio.timeout(_TOTAL_TIMEOUT_SECONDS):
                async with self._client.stream(
                    "GET",
                    self._base_url + path,
                    headers={"Authorization": f"Bearer {bearer}"},
                    follow_redirects=False,
                    timeout=_TIMEOUT_SECONDS,
                ) as response:
                    if response.status_code in {401, 403, 404}:
                        codes = {
                            401: "authentication_required",
                            403: "access_denied",
                            404: "not_found",
                        }
                        raise SessionError(response.status_code, codes[response.status_code])
                    if response.status_code != 200:
                        raise SessionError(503, "platform_unavailable")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
                            raise SessionError(503, "platform_response_invalid")
                        body.extend(chunk)
                    payload = json.loads(body)
                    if not isinstance(payload, dict):
                        raise SessionError(503, "platform_response_invalid")
                    return payload
        except (httpx.HTTPError, OSError):
            raise SessionError(503, "platform_unavailable") from None
        except (ValueError, UnicodeError):
            raise SessionError(503, "platform_response_invalid") from None

    async def identity(self, bearer: str) -> Principal:
        """Require the platform's verified identity and matching v2 policy envelope."""
        payload = await self._get("/api/v1/me", bearer)
        tenant_id = payload.get("tenant_id")
        user_id = payload.get("user_id")
        if isinstance(user_id, int) and not isinstance(user_id, bool):
            user_id = str(user_id)
        envelope = payload.get("ai_policy_envelope")
        if (
            not _identifier(tenant_id)
            or not _identifier(user_id)
            or not isinstance(envelope, dict)
            or envelope.get("tenant_id") != tenant_id
            or envelope.get("contract") != "sahool.ai_policy_envelope"
            or type(envelope.get("contract_version")) is not int
            or envelope["contract_version"] < 2
            or not isinstance(envelope.get("allowed_tools"), list)
            or not all(_identifier(name) for name in envelope["allowed_tools"])
        ):
            raise SessionError(403, "trusted_policy_required")
        return Principal(tenant_id=tenant_id, user_id=user_id)

    async def authorize_field(self, bearer: str, principal: Principal, field_id: str) -> None:
        """Reuse FIELD_VIEW and tenant RLS via the existing field-detail route.

        FieldDetail deliberately contains no tenant_id. Authorization comes from
        the platform executing the canonical tenant-scoped read with the same
        bearer, rather than trusting a tenant identifier in its response body.
        """
        if not _identifier(principal.tenant_id) or not _identifier(principal.user_id):
            raise SessionError(403, "trusted_identity_required")
        if (
            not _identifier(field_id)
            or any(c in field_id for c in ("/", "\\", "%"))
            or field_id in {".", ".."}
        ):
            raise SessionError(422, "field_id_invalid")
        try:
            field_id.encode("utf-8")
        except UnicodeError:
            raise SessionError(422, "field_id_invalid") from None
        # Path separators, query and fragment syntax remain inside one encoded
        # path segment; they cannot alter the authority's endpoint or origin.
        payload = await self._get("/api/v1/fields/" + quote(field_id, safe=""), bearer)
        if payload.get("field_id") != field_id:
            raise SessionError(403, "field_authorization_invalid")

    async def ready(self) -> bool:
        """A bounded health read; never return an upstream body or error text."""
        try:
            async with asyncio.timeout(_TOTAL_TIMEOUT_SECONDS):
                async with self._client.stream(
                    "GET",
                    self._base_url + "/healthz",
                    follow_redirects=False,
                    timeout=_TIMEOUT_SECONDS,
                ) as response:
                    return response.status_code == 200
        except (httpx.HTTPError, OSError):
            return False
