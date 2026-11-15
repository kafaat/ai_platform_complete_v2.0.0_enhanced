"""Gateway-trusted user identity for field-management-service's public task routes.

The service's original routes (main.py, ``/internal/fields``) stay service-token only. The task
and inspection routes rebuilt from carrier D #1439 are called by people, from the web and mobile
apps, so they use the gateway pattern scout-ingest's photo routes already use
(nginx/nginx.v9.conf ``location ^~ /api/v1/scouting-media/``):

* nginx verifies the user's JWT with ``auth_request /_auth_verify``, clears every identity header
  the client sent (proxy_params.conf), then sets ``X-Tenant-Id``/``X-User-Id``/``X-User-Role``
  from the verify response only;
* nginx injects a dedicated token, ``X-Field-Tasks-Token`` = ``FIELD_TASKS_SERVICE_TOKEN`` (never
  the shared ``SAHOOL_AGENT_TOKEN``), so a caller that bypasses the gateway holds nothing;
* this module checks the token in constant time, requires a UUID tenant and a user id, and maps
  the role claim to the platform's permissions (``ROLE_PERMISSIONS`` below, pinned to
  ``services/sahool-platform/core/authorization.py`` by a unit test so the two cannot drift);
* every query runs in one transaction with ``app.current_tenant``, ``app.current_user_id`` and
  ``app.current_role`` set transaction-local (the platform's ``tenant_connection``), so FORCE RLS
  applies and the hand-off INSERT policies can bind ``actor`` to the caller.

No JWT is decoded here; no platform fallback exists. Token unset ⇒ 503; mismatch ⇒ 401.
"""

from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException

# The platform's role aliases (api/main.py:_ROLE_ALIASES): the auth service issues
# admin/expert/farmer, the platform's five-role model names owner/agronomist/worker.
ROLE_ALIASES = {
    "owner": "owner",
    "admin": "owner",
    "manager": "manager",
    "agronomist": "agronomist",
    "expert": "agronomist",
    "worker": "worker",
    "farmer": "worker",
    "viewer": "viewer",
}

# The permissions these routes check, by canonical role (core/authorization.py _ROLE_PERMISSIONS).
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset(
        {
            "field:view",
            "field:edit",
            "observation:record",
            "inspection:review",
            "analytics:view",
            "activity:execute",
        }
    ),
    "manager": frozenset(
        {
            "field:view",
            "field:edit",
            "observation:record",
            "inspection:review",
            "analytics:view",
            "activity:execute",
        }
    ),
    "agronomist": frozenset(
        {"field:view", "observation:record", "inspection:review", "analytics:view"}
    ),
    "worker": frozenset({"field:view", "observation:record", "activity:execute"}),
    "viewer": frozenset({"field:view"}),
}
CHECKED_PERMISSIONS = frozenset().union(*ROLE_PERMISSIONS.values())

FIELD_VIEW = "field:view"
FIELD_EDIT = "field:edit"
OBSERVATION_RECORD = "observation:record"
INSPECTION_REVIEW = "inspection:review"
ANALYTICS_VIEW = "analytics:view"
ACTIVITY_EXECUTE = "activity:execute"


@dataclass(frozen=True)
class Caller:
    tenant_id: str
    user_id: str
    role: str  # canonical role ("" when the claim names no tenant role)

    def can(self, permission: str) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, frozenset())


def canonical_role(claim: str | None) -> str:
    return ROLE_ALIASES.get((claim or "").strip().lower(), "")


def authorize(token: str | None, tenant: str | None, uid: str | None, role: str | None) -> Caller:
    """Token, trusted identity and role claim. Pure apart from the environment."""
    expected = os.getenv("FIELD_TASKS_SERVICE_TOKEN", "")
    if not expected:
        raise HTTPException(503, "field_tasks_token_unconfigured")
    if not hmac.compare_digest((token or "").encode(), expected.encode()):
        raise HTTPException(401, "field_tasks_token_required")
    if not uid or not uid.strip():
        raise HTTPException(403, "trusted_tenant_and_user_required")
    try:
        tenant_id = str(UUID(tenant or ""))
    except (TypeError, ValueError):
        raise HTTPException(403, "invalid_trusted_tenant") from None
    return Caller(tenant_id, uid.strip(), canonical_role(role))


def require(caller: Caller, permission: str) -> Caller:
    if not caller.can(permission):
        raise HTTPException(403, "permission_denied")
    return caller


def caller_dependency(permission: str):
    """FastAPI dependency: the authorized caller holding ``permission``."""

    def _dep(
        x_field_tasks_token: str | None = Header(None, alias="X-Field-Tasks-Token"),
        x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
        x_user_id: str | None = Header(None, alias="X-User-Id"),
        x_user_role: str | None = Header(None, alias="X-User-Role"),
    ) -> Caller:
        return require(
            authorize(x_field_tasks_token, x_tenant_id, x_user_id, x_user_role), permission
        )

    return _dep


@asynccontextmanager
async def caller_connection(caller: Caller):
    """One short-lived connection, one transaction, the caller's tenant/user/role set locally.

    Mirrors main.py (no pool across event loops; statement cache off behind pgbouncer). An
    unconfigured or unreachable database answers 503, never a fallback.
    """
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        raise HTTPException(503, "field task database is not configured (DATABASE_URL unset)")
    import asyncpg

    try:
        conn = await asyncpg.connect(dsn, statement_cache_size=0)
    except Exception as exc:  # noqa: BLE001 - any connect failure is the documented 503
        raise HTTPException(503, "field task database unavailable") from exc
    try:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true), "
                "set_config('app.current_user_id', $2, true), "
                "set_config('app.current_role', $3, true)",
                caller.tenant_id,
                caller.user_id,
                caller.role,
            )
            yield conn
    finally:
        await conn.close()
