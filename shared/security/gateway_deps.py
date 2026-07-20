"""FastAPI dependency wrappers over the pure gateway-trusted identity helpers.

Kept separate from ``shared.security.trusted_tenant`` so the pure decision logic
stays importable without FastAPI (no-fastapi CI tier). These wrappers translate
the stdlib ``TrustedTenantError`` / token check into fail-closed ``403`` responses.
"""

from __future__ import annotations

import os
import time

from fastapi import Header, HTTPException, Request

from .trusted_tenant import (
    ERROR_REVIEWER_ROLE_REQUIRED,
    SEASON_REVIEWER_ROLE,
    TrustedTenantError,
    edge_body_sha256,
    has_reviewer_role,
    resolve_trusted_tenant,
    service_token_ok,
    verify_edge_attestation,
)


def require_trusted_tenant(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> str:
    """Header-only trusted tenant dependency (no request body). 403 fail-closed.

    For endpoints whose body also carries ``tenant_id`` use
    ``resolve_trusted_tenant(x_tenant_id, body_tenant_id)`` directly inside the
    handler so the body value can be checked for a mismatch.
    """
    try:
        return resolve_trusted_tenant(x_tenant_id, None)
    except TrustedTenantError as exc:
        raise HTTPException(status_code=403, detail=exc.code) from exc


def require_authenticated_user(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    """Trusted authenticated-user dependency for human-governance endpoints.

    SEC-3.1: the gateway (``nginx`` ``auth_request``) injects ``X-User-Id`` from
    the verified JWT ``sub`` claim; ``proxy_params.conf`` clears any client-sent
    value first, so this header is the only trusted source of caller identity
    inside the service. Approve/deny/resume must be tied to an authenticated user
    (not just a JSON body), so a missing/blank id is rejected fail-closed (403).
    """
    if not x_user_id or not x_user_id.strip():
        raise HTTPException(status_code=403, detail="missing_user")
    return x_user_id.strip()


def require_service_token(
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
) -> None:
    """Internal service-token gate for write/mutating endpoints (fail-closed 403).

    Mirrors ``services/sahool-platform/api/main.py`` ``_require_service_token``:
    the secret is read from ``SAHOOL_AGENT_TOKEN`` at request time and compared in
    constant time; a missing/blank secret rejects all callers.
    """
    if not service_token_ok(x_agent_token, os.getenv("SAHOOL_AGENT_TOKEN", "")):
        raise HTTPException(status_code=403, detail="service_token_required")


async def require_attested_reviewer(
    request: Request,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_roles: str | None = Header(default=None, alias="X-Roles"),
    x_edge_attestation: str | None = Header(default=None, alias="X-Edge-Attestation"),
    x_edge_timestamp: str | None = Header(default=None, alias="X-Edge-Timestamp"),
) -> str:
    """SEASON-RECORD-ENTRY-01 §4-① — the sensitive-accept identity gate (destination-bound).

    The service-token proves *a mesh service* is calling; it does NOT prove *which
    human* reviewed. Accept releases ``calibration_eligible`` so it needs a real,
    edge-attested reviewer. The auth gateway signs the verified identity **bound to this
    request's method/path/body** with ``SEASON_EDGE_HMAC_KEY`` (secret-manager, never in
    compose); a container that bypasses the gateway and forges ``X-User-Id`` has no valid
    signature -> 401, and an attestation minted for another path can't be replayed here.

    Method/path/body are read from THIS request (not trusted headers). Returns the attested
    reviewer's user id, or raises 401 (unattested/stale/wrong-destination) / 403 (not a
    ``season-reviewer``).
    """
    body = await request.body()
    try:
        user_id = verify_edge_attestation(
            user_id=x_user_id,
            roles=x_roles,
            method=request.method,
            path=request.url.path,
            body_sha256=edge_body_sha256(body),
            timestamp=x_edge_timestamp,
            attestation=x_edge_attestation,
            secret=os.getenv("SEASON_EDGE_HMAC_KEY"),
            now_epoch=time.time(),
        )
    except TrustedTenantError as exc:
        raise HTTPException(status_code=401, detail=exc.code) from exc
    if not has_reviewer_role(x_roles, SEASON_REVIEWER_ROLE):
        raise HTTPException(status_code=403, detail=ERROR_REVIEWER_ROLE_REQUIRED)
    return user_id
