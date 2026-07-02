"""Gateway-trusted tenant identity (SEC-3).

The nginx gateway verifies the JWT, clears any client-supplied ``X-Tenant-Id``,
then injects the AUTHENTICATED ``X-Tenant-Id`` from the verify response (see
``nginx/nginx.v9.conf`` R6 trust model). Inside internal services that header is
therefore the ONLY tenant source of truth. A ``tenant_id`` carried in the request
BODY is untrusted (spoofable) and may only ECHO the header — never override it.

This module is stdlib-only (no FastAPI) so the pure decision function is unit-
testable in the no-fastapi CI tier. The thin FastAPI ``Depends`` wrappers live in
``shared.security.gateway_deps`` (imported only by services that ship FastAPI).
"""

from __future__ import annotations

import hmac

# Stable error codes surfaced as the HTTP 403 ``detail`` by the FastAPI wrappers.
ERROR_MISSING_TENANT = "missing_tenant"
ERROR_TENANT_MISMATCH = "tenant_mismatch"


class TrustedTenantError(Exception):
    """Raised (fail-closed) when a gateway-trusted tenant cannot be established.

    ``code`` is a stable machine token (``missing_tenant`` / ``tenant_mismatch``)
    that the FastAPI wrapper maps onto the ``403`` response ``detail``.
    """

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def _clean(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_trusted_tenant(x_tenant_id: str | None, body_tenant_id: str | None = None) -> str:
    """Return the gateway-authenticated tenant, fail-closed.

    - Missing/blank ``X-Tenant-Id``           -> ``TrustedTenantError(missing_tenant)``.
    - body tenant present AND != header       -> ``TrustedTenantError(tenant_mismatch)``.
    - body tenant omitted OR equal to header  -> returns the header value.

    The body value is never trusted as an override; it may only echo the header.
    """
    header = _clean(x_tenant_id)
    if header is None:
        raise TrustedTenantError(ERROR_MISSING_TENANT, "X-Tenant-Id header is required")
    body = _clean(body_tenant_id)
    if body is not None and body != header:
        raise TrustedTenantError(ERROR_TENANT_MISMATCH, "tenant_mismatch")
    return header


def service_token_ok(provided: str | None, expected: str | None) -> bool:
    """Constant-time internal service-token check, fail-closed when unset.

    Returns ``False`` when the expected secret is empty/unset so a mis-provisioned
    service never silently accepts requests (mirrors the platform idiom in
    ``services/sahool-platform/api/main.py`` ``_require_service_token``).
    """
    expected_s = expected or ""
    if not expected_s:
        return False
    return hmac.compare_digest(str(provided or ""), str(expected_s))
