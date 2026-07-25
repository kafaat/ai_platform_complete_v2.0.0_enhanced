"""P0-1 behavioral: the request body must never override the authenticated context tenant.

The field-imagery mutating routes (process-date, historical-backfill, geoparquet export) derive
the tenant from the request context (the gateway-trusted X-Tenant-Id, the same tenant
_require_field_tenant verifies ownership against). A body tenant_id that differs must fail closed
(403) — never create a run/item or export analytics under a different tenant. This exercises the
real `_authenticated_tenant` helper, not just its source text.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _fn():
    import main  # noqa: F401 — wires the app + request-context ContextVar

    from routers.fields import _authenticated_tenant

    return _authenticated_tenant


def test_absent_body_tenant_uses_context() -> None:
    import main

    fn = _fn()
    tok = main._REQ_TENANT.set("tenant-A")
    try:
        assert fn(None) == "tenant-A"
    finally:
        main._REQ_TENANT.reset(tok)


def test_matching_body_tenant_is_accepted() -> None:
    import main

    fn = _fn()
    tok = main._REQ_TENANT.set("tenant-A")
    try:
        assert fn("tenant-A") == "tenant-A"
    finally:
        main._REQ_TENANT.reset(tok)


def test_mismatched_body_tenant_is_rejected_403() -> None:
    import main

    fn = _fn()
    tok = main._REQ_TENANT.set("tenant-A")
    try:
        with pytest.raises(HTTPException) as ei:
            fn("tenant-B")  # a different tenant in the body must not override the context
        assert ei.value.status_code == 403
    finally:
        main._REQ_TENANT.reset(tok)
