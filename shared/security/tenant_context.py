"""Tenant context resolution helpers.

Header-based tenant context remains the preferred production path because the
API gateway injects it after authentication. Query parameters are accepted only
for browser image/tile requests that cannot reliably attach custom headers.
"""

from __future__ import annotations

from typing import Any


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def resolve_tenant_context(
    request: Any, tid: str | None = None, tenant_id: str | None = None
) -> str | None:
    """Resolve tenant context with production-safe priority.

    Priority:
    1. ``X-Tenant-Id`` header, injected by the trusted gateway.
    2. ``tid`` query parameter, used by Leaflet/MapLibre image tile requests.
    3. ``tenant_id`` query parameter, compatibility alias.
    4. ``None`` so RLS/ownership checks fail closed.
    """

    headers = getattr(request, "headers", {}) or {}
    header_value = None
    try:
        header_value = headers.get("X-Tenant-Id")
    except AttributeError:
        header_value = None

    return _clean(header_value) or _clean(tid) or _clean(tenant_id)
