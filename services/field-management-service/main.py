#!/usr/bin/env python3
"""SAHOOL field-management-service — tenant-scoped owner of the `fields` table.

Canonical owner per ``docs/architecture/db_ownership.yml`` (owner=field-management-service).
This service exposes ONLY service-token internal reads of field rows for other
services (e.g. vegetation-analysis) that hold a service token but no user JWT.

Security contract (fail-closed, no platform fallback):
  • service-token only — X-Agent-Token compared to SAHOOL_AGENT_TOKEN with
    hmac.compare_digest. Missing secret OR mismatch ⇒ 401. A user Bearer JWT alone
    is therefore rejected (there is NO get_current_user / require_permission / JWT
    decode anywhere in this service).
  • tenant comes ONLY from the verified X-Tenant-Id header (missing/empty ⇒ 400),
    never from query/body.
  • every query is scoped by tenant_id under RLS (SET LOCAL app.current_tenant
    inside a transaction) AND by an explicit tenant_id column predicate, so a field
    owned by another tenant is indistinguishable from a missing one ⇒ 404 (no
    cross-tenant existence disclosure).
  • DATABASE_URL unset ⇒ 503 (fail-closed, no synthetic fallback). Any asyncpg/
    connection error ⇒ 503 "field catalog unavailable" (never 500, never fallback).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from shared.security.service_tenant_assertion import (
    TenantAssertionError,
    verify_tenant_assertion,
)

VERSION = os.getenv("SERVICE_VERSION", "9.1.0-field-owner")
DATABASE_URL = os.getenv("DATABASE_URL", "")

app = FastAPI(title="SAHOOL Field Management Service", version=VERSION)


def _source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_source_identity() -> dict[str, str]:
    source = Path(__file__).resolve()
    here = source.parent
    assertion = here / "shared" / "security" / "service_tenant_assertion.py"
    if not assertion.is_file():
        assertion = source.parents[2] / "shared" / "security" / "service_tenant_assertion.py"
    return {
        "main_sha256": _source_sha256(source),
        "service_tenant_assertion_sha256": _source_sha256(assertion),
    }

# Columns read for both the by-id detail and the list. geometry is JSONB GeoJSON
# (asyncpg returns it as a str with no codec ⇒ json.loads before returning).
_FIELD_COLUMNS = (
    "field_id, farm_id, name, area_ha, crop, soil_type, manager, "
    "field_code, description, water_source, ownership_type, country, region, "
    "lat, lon, geometry"
)


# Optional caller allowlist (defence in depth over the shared service token). When
# FIELD_SERVICE_ALLOWED_CALLERS is set (comma-separated service names), the caller must
# present a matching X-Service-Name; unset ⇒ permissive (token still gates). A dedicated
# per-consumer credential (e.g. VEGETATION_TO_FIELD_SERVICE_TOKEN) is the upgrade path.
_ALLOWED_CALLERS = {
    s.strip() for s in os.getenv("FIELD_SERVICE_ALLOWED_CALLERS", "").split(",") if s.strip()
}


def _require_service_token(
    x_agent_token: str | None = Header(None, alias="X-Agent-Token"),
    x_service_name: str | None = Header(None, alias="X-Service-Name"),
) -> None:
    """Service-token guard (fail-closed): reject if the secret is unset OR mismatched.

    NOTE: this service returns 401 (not 403) on an auth failure — a user Bearer JWT
    with no X-Agent-Token is therefore rejected. Constant-time compare avoids leaking
    the secret via timing. When an allowlist is configured, the authenticated caller
    must also identify via X-Service-Name (403 otherwise) — caller identity is checked
    only AFTER the token passes.
    """
    expected = os.getenv("SAHOOL_AGENT_TOKEN", "")
    if not expected or not hmac.compare_digest(x_agent_token or "", expected):
        raise HTTPException(
            status_code=401,
            detail="internal field endpoint requires a valid X-Agent-Token",
        )
    production = os.getenv("SAHOOL_ENV", "development").strip().lower() in {
        "production",
        "prod",
    }
    if production and not _ALLOWED_CALLERS:
        raise HTTPException(
            status_code=503,
            detail="FIELD_SERVICE_ALLOWED_CALLERS is required in production",
        )
    if _ALLOWED_CALLERS and (x_service_name or "") not in _ALLOWED_CALLERS:
        raise HTTPException(status_code=403, detail="caller not in field-service allowlist")


def _require_tenant(
    request: Request,
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    x_tenant_assertion: str | None = Header(None, alias="X-Tenant-Assertion"),
    x_service_name: str | None = Header(None, alias="X-Service-Name"),
    x_request_id: str | None = Header(None, alias="X-Request-Id"),
    _: None = Depends(_require_service_token),
) -> str:
    """Return a tenant only after verifying its short-lived caller-bound assertion.

    Development retains an explicit header-only compatibility mode. Production
    requires ``FIELD_SERVICE_TENANT_ASSERTION_KEY`` and a valid assertion."""
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-Id required for internal field read")
    production = os.getenv("SAHOOL_ENV", "development").strip().lower() in {
        "production",
        "prod",
    }
    key = os.getenv("FIELD_SERVICE_TENANT_ASSERTION_KEY", "")
    previous_key = os.getenv("FIELD_SERVICE_TENANT_ASSERTION_PREVIOUS_KEY", "")
    current_kid = os.getenv("FIELD_SERVICE_TENANT_ASSERTION_KEY_ID", "current")
    previous_kid = os.getenv("FIELD_SERVICE_TENANT_ASSERTION_PREVIOUS_KEY_ID", "previous")
    if production and not key:
        raise HTTPException(status_code=503, detail="tenant assertion verification unavailable")
    if key:
        try:
            claims = verify_tenant_assertion(
                x_tenant_assertion or "",
                {current_kid: key, **({previous_kid: previous_key} if previous_key else {})},
                x_service_name or "",
                x_tenant_id,
                expected_method=request.method,
                expected_path=request.url.path,
                expected_request_id=x_request_id or "",
            )
            _claim_assertion_once(claims.replay_key, production)
        except TenantAssertionError as exc:
            raise HTTPException(
                status_code=403, detail=f"invalid tenant assertion: {exc}"
            ) from None
    return x_tenant_id


def _claim_assertion_once(replay_key: str, production: bool) -> None:
    """Atomically consume one nonce. Production never falls back to process memory."""
    redis_url = os.getenv("FIELD_SERVICE_ASSERTION_REDIS_URL", "")
    if not redis_url:
        if production:
            raise HTTPException(status_code=503, detail="tenant assertion replay store unavailable")
        return
    try:
        import redis

        client = redis.Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        if not client.set(replay_key, "1", nx=True, ex=70):
            raise HTTPException(status_code=403, detail="tenant assertion replayed")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="tenant assertion replay store unavailable"
        ) from exc


def _row_to_dict(row) -> dict:
    """asyncpg.Record ⇒ plain dict; JSONB geometry (str) ⇒ decoded GeoJSON object."""
    data = dict(row)
    geom = data.get("geometry")
    if isinstance(geom, str):
        try:
            data["geometry"] = json.loads(geom)
        except (ValueError, TypeError):
            data["geometry"] = None
    return data


async def _connect():
    """Open one short-lived connection per request (no pool cached across event loops).

    Mirrors services/raster-service/db_persist.py::_connect — a pool bound to a dead
    event loop raises "another operation is in progress". DATABASE_URL unset ⇒ 503
    (fail-closed). statement_cache_size=0 keeps it safe behind pgbouncer.
    """
    if not DATABASE_URL:
        raise HTTPException(
            status_code=503,
            detail="field catalog database is not configured (DATABASE_URL unset)",
        )
    import asyncpg

    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


@app.get("/healthz")
async def healthz():
    return {"status": "alive", "service": "field-management-service", "version": VERSION}


@app.get("/health", include_in_schema=False)
async def legacy_health():
    return await healthz()


@app.get("/readyz")
async def readyz():
    return {
        "status": "ready",
        "service": "field-management-service",
        "implemented_runtime": True,
        "ready": bool(DATABASE_URL),
        "runtime_role": "field-owner",
        "dependencies": {"database": bool(DATABASE_URL)},
        "source_identity": _runtime_source_identity(),
    }


@app.get("/contract")
async def contract():
    return {
        "service": "field-management-service",
        "contract_version": "2026-07-15.field-owner-p0",
        "implemented_runtime": True,
        "runtime_role": "field-owner",
        "truth_policy": "single-owner-fail-closed",
        "auth": "service-token-only",
        "allowed_routes": [
            "/healthz",
            "/readyz",
            "/contract",
            "/internal/fields/{field_id}",
            "/internal/fields",
        ],
    }


@app.get("/")
async def root():
    return {
        "service": "field-management-service",
        "implemented_runtime": True,
        "runtime_role": "field-owner",
    }


@app.get("/internal/fields/{field_id}")
async def internal_get_field(
    field_id: str,
    tenant: str = Depends(_require_tenant),
):
    """Service-to-service field read scoped by BOTH field_id AND tenant_id.

    A field owned by another tenant is indistinguishable from a missing one ⇒ 404
    (no cross-tenant existence disclosure). Never widens authz; never falls back.
    """
    conn = None
    try:
        conn = await _connect()
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant))
            row = await conn.fetchrow(
                f"SELECT {_FIELD_COLUMNS} FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid",
                field_id,
                str(tenant),
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — any DB error ⇒ documented 503, never 500/fallback
        raise HTTPException(status_code=503, detail="field catalog unavailable") from exc
    finally:
        if conn is not None:
            await conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="field not found for this tenant")
    return _row_to_dict(row)


@app.get("/internal/fields")
async def internal_list_fields(
    tenant: str = Depends(_require_tenant),
):
    """Tenant-scoped field enumeration (same service-token + RLS contract as the by-id read)."""
    conn = None
    try:
        conn = await _connect()
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant))
            rows = await conn.fetch(
                f"SELECT {_FIELD_COLUMNS} FROM fields WHERE tenant_id = $1::uuid ORDER BY name",
                str(tenant),
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — any DB error ⇒ documented 503, never 500/fallback
        raise HTTPException(status_code=503, detail="field catalog unavailable") from exc
    finally:
        if conn is not None:
            await conn.close()
    return [_row_to_dict(r) for r in rows]
