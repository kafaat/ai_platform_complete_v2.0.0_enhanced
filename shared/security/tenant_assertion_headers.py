"""Caller side of a signed internal tenant call: the four headers a receiver verifies.

The receiver checks ``X-Tenant-Assertion`` with
``shared.security.service_tenant_assertion.verify_tenant_assertion`` against the caller name in
``X-Service-Name``, the tenant it is about to act for, the method, the path and ``X-Request-Id``.
Only a tenant the caller has itself verified (a JWT claim, a trusted gateway header) may be
passed here: the assertion makes the caller answerable for the tenant, it does not verify it.
"""

from __future__ import annotations

import uuid

from shared.security.service_tenant_assertion import (
    TenantAssertionError,
    create_tenant_assertion,
)

__all__ = ["TenantAssertionError", "tenant_assertion_headers"]


def tenant_assertion_headers(
    *,
    key: str,
    key_id: str,
    service: str,
    tenant_id: str,
    method: str,
    path: str,
) -> dict[str, str]:
    """Return the headers for one request. Raises ``TenantAssertionError`` on a short key or a
    tenant/service value that cannot be signed, so the caller never sends an unsigned request."""
    request_id = uuid.uuid4().hex
    return {
        "X-Service-Name": service,
        "X-Tenant-Id": str(tenant_id),
        "X-Request-Id": request_id,
        "X-Tenant-Assertion": create_tenant_assertion(
            key,
            service,
            str(tenant_id),
            key_id=key_id or "current",
            method=method,
            path=path,
            request_id=request_id,
        ),
    }
