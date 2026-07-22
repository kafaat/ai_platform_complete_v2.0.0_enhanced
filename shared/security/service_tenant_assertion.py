"""Request-bound, replay-resistant assertions for internal tenant calls."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
import time
from typing import Mapping

VERSION = "v2"


class TenantAssertionError(ValueError):
    """The assertion is malformed, expired, replayed, or outside its scope."""


@dataclass(frozen=True)
class TenantAssertionClaims:
    key_id: str
    issued_at: int
    nonce: str
    service: str
    tenant_id: str
    method: str
    path: str
    request_id: str

    @property
    def replay_key(self) -> str:
        digest = hashlib.sha256(
            f"{self.key_id}\n{self.service}\n{self.nonce}".encode()
        ).hexdigest()
        return f"sahool:tenant-assertion:{digest}"


def _clean(value: str, name: str) -> str:
    value = str(value or "").strip()
    if not value or any(ch in value for ch in (":", "\n", "\r")):
        raise TenantAssertionError(f"invalid {name}")
    return value


def _payload(claims: TenantAssertionClaims) -> bytes:
    return "\n".join(
        (
            VERSION, claims.key_id, str(claims.issued_at), claims.nonce,
            claims.service, claims.tenant_id, claims.method, claims.path,
            claims.request_id,
        )
    ).encode()


def create_tenant_assertion(
    key: str,
    service: str,
    tenant_id: str,
    *,
    key_id: str = "current",
    method: str,
    path: str,
    request_id: str,
    nonce: str | None = None,
    issued_at: int | None = None,
) -> str:
    if len(key) < 32:
        raise TenantAssertionError("assertion key must contain at least 32 characters")
    claims = TenantAssertionClaims(
        key_id=_clean(key_id, "key_id"),
        issued_at=int(time.time()) if issued_at is None else int(issued_at),
        nonce=_clean(nonce or secrets.token_urlsafe(18), "nonce"),
        service=_clean(service, "service"),
        tenant_id=_clean(tenant_id, "tenant_id"),
        method=_clean(method.upper(), "method"),
        path=_clean(path, "path"),
        request_id=_clean(request_id, "request_id"),
    )
    signature = hmac.new(key.encode(), _payload(claims), hashlib.sha256).hexdigest()
    fields = (
        VERSION, claims.key_id, str(claims.issued_at), claims.nonce, claims.service,
        claims.tenant_id, claims.method, claims.path, claims.request_id, signature,
    )
    return ":".join(fields)


def verify_tenant_assertion(
    assertion: str,
    keys: Mapping[str, str],
    expected_service: str,
    expected_tenant_id: str,
    *,
    expected_method: str,
    expected_path: str,
    expected_request_id: str,
    now: int | None = None,
    max_age_seconds: int = 60,
    future_skew_seconds: int = 5,
) -> TenantAssertionClaims:
    parts = assertion.split(":") if assertion else []
    if len(parts) != 10 or parts[0] != VERSION:
        raise TenantAssertionError("malformed tenant assertion")
    _, kid, raw_ts, nonce, service, tenant_id, method, path, request_id, presented = parts
    key = keys.get(kid, "")
    if len(key) < 32:
        raise TenantAssertionError("unknown assertion key")
    try:
        issued_at = int(raw_ts)
    except ValueError as exc:
        raise TenantAssertionError("invalid assertion timestamp") from exc
    claims = TenantAssertionClaims(kid, issued_at, nonce, service, tenant_id, method, path, request_id)
    current = int(time.time()) if now is None else int(now)
    if issued_at > current + future_skew_seconds:
        raise TenantAssertionError("assertion timestamp is in the future")
    if current - issued_at > max_age_seconds:
        raise TenantAssertionError("tenant assertion expired")
    expected_scope = (
        expected_service, expected_tenant_id, expected_method.upper(),
        expected_path, expected_request_id,
    )
    if (service, tenant_id, method, path, request_id) != expected_scope:
        raise TenantAssertionError("tenant assertion scope mismatch")
    expected = hmac.new(key.encode(), _payload(claims), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(presented, expected):
        raise TenantAssertionError("tenant assertion signature mismatch")
    return claims
