#!/usr/bin/env python3
"""SAHOOL indicators-service — contract and aggregation boundary.

This service does not compute observed spectral indices. Raster-service owns
band math, scenes, COGs, quality masks, tiles, and observed time series.
Vegetation-analysis owns interpretation. The current service publishes the
canonical ownership contract and fails closed for spectral computation.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, HTTPException, Query

_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))
from observation_runtime import fetch_canonical_observations  # noqa: E402
from observation_timeline import TimelineSourceError, fetch_canonical_timeline  # noqa: E402

from shared.security.trusted_tenant import service_token_ok  # noqa: E402

VERSION = os.getenv("SERVICE_VERSION", "9.1.0-contract-boundary")


def _resolve_manifest() -> Path:
    """Locate shared/contracts/indicator_ownership.json in both repo and container layouts.

    In the repo the file lives at <root>/shared/contracts/...; the container Dockerfile
    flattens it to /app/shared/contracts/... alongside main.py. Walking up from this file
    (parent first) finds it in either layout — a hardcoded parent-index into the repo tree
    raised IndexError at /app/main.py and took the whole service down on startup.
    """
    here = Path(__file__).resolve()
    for base in (here.parent, *here.parents):
        candidate = base / "shared" / "contracts" / "indicator_ownership.json"
        if candidate.exists():
            return candidate
    return here.parent / "shared" / "contracts" / "indicator_ownership.json"


_MANIFEST = _resolve_manifest()

app = FastAPI(title="SAHOOL Indicators Contract Service", version=VERSION)


def _manifest() -> dict:
    try:
        data = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=503, detail=f"indicator ownership manifest unavailable: {exc}"
        ) from exc
    if not data.get("products") or not data.get("policy"):
        raise HTTPException(status_code=503, detail="indicator ownership manifest is incomplete")
    return data


@app.get("/healthz")
async def healthz():
    return {"status": "alive", "service": "indicators-service", "version": VERSION}


@app.get("/health", include_in_schema=False)
async def legacy_health():
    return await healthz()


@app.get("/metrics")
async def metrics():
    """مقاييس Prometheus. الهدفُ مُعلَنٌ في `prometheus/prometheus.yml` منذ البداية
    وكانت النقطةُ غائبة ⇒ ٤٠٤ ⇒ `up=0` دائماً، وقاعدةُ التنبيه على `up==0` تُطلِق
    أبداً فتُدرِّب المُشغِّل على تجاهلها. «مُعلَنٌ ليس يعمل»."""
    from fastapi import Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/readyz")
async def ready():
    manifest = _manifest()
    return {
        "status": "ready",
        "service": "indicators-service",
        "implemented_runtime": True,
        "runtime_role": "canonical-observation-adapter",
        "spectral_compute": False,
        "observed_spectral_owner": manifest["policy"]["observed_spectral_owner"],
        "schema_version": manifest["schema_version"],
    }


@app.get("/v1/indicators/ownership")
async def ownership():
    return _manifest()


@app.get("/v1/indicators/catalog")
async def catalog():
    manifest = _manifest()
    return {
        "schema_version": manifest["schema_version"],
        "indicators": manifest["products"],
        "source": "canonical-indicator-ownership-manifest",
    }


@app.get("/capabilities")
async def capabilities():
    return {
        "schema_version": _manifest()["schema_version"],
        "service": "indicators-service",
        "implemented_runtime": True,
        "runtime_role": "canonical-observation-adapter",
        "capabilities": {
            "ownership_contract": True,
            "indicator_catalog": True,
            "indicator_compute": False,
            "tile_generation": False,
            "timeseries": True,
            "canonical_observation_adapter": True,
        },
        "owners": {
            "observed_spectral": "raster-service",
            "interpretation": "vegetation-analysis-service",
            "aggregation": "sahool-platform",
        },
    }


@app.get("/contract")
async def contract():
    return {
        "service": "indicators-service",
        "contract_version": "2026-07-12.riv-p0",
        "implemented_runtime": True,
        "runtime_role": "canonical-observation-adapter",
        "truth_policy": "single-owner-fail-closed",
        "allowed_routes": [
            "/healthz",
            "/readyz",
            "/capabilities",
            "/contract",
            "/v1/indicators/ownership",
            "/v1/indicators/catalog",
            "/v1/fields/{field_id}/observations",
            "/v1/fields/{field_id}/observation-timeline",
            "/",
        ],
    }


@app.post("/v1/indicators/compute")
async def compute_indicator():
    raise HTTPException(
        status_code=409,
        detail="observed spectral computation is exclusively owned by raster-service",
    )


@app.get("/")
async def root():
    return {
        "service": "indicators-service",
        "implemented_runtime": True,
        "runtime_role": "canonical-observation-adapter",
        "spectral_compute": False,
    }


# ── OI-01: the tenant on the internal hop comes from a verified identity ───────────────
#
# ``/observations`` forwards the caller's tenant to raster-service together with this
# service's own SAHOOL_AGENT_TOKEN. A bare X-Tenant-Id is therefore never trusted: it is
# accepted only from a mesh caller that proves the same service token (the trust
# raster-service itself applies to it), or from a bearer whose identity — resolved by the
# platform, the session/RBAC owner — carries that tenant and field:view. Same pattern as
# ``remote-sensing-workspace-bff`` ``_workspace_identity``. (``/observation-timeline`` is
# already bound: its bearer must resolve the field's season through the platform's
# tenant-scoped ``/seasons`` before raster-service is called.)
_IDENTITY_TIMEOUT_S = 10.0
_OBSERVATION_PERMISSION = "field:view"


def _parse_tenant(x_tenant_id: str) -> UUID:
    try:
        return UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(400, "invalid X-Tenant-Id") from exc


async def _bearer_identity(authorization: str) -> tuple[str, list[str]]:
    """Resolve (tenant_id, permissions) of a bearer via the platform's ``/api/v1/auth/me``."""
    platform = os.getenv("PLATFORM_API_URL", "http://sahool-platform:8000").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=_IDENTITY_TIMEOUT_S, trust_env=False) as client:
            response = await client.get(
                f"{platform}/api/v1/auth/me", headers={"Authorization": authorization}
            )
        if response.status_code in {401, 403}:
            raise HTTPException(response.status_code, "observation_access_denied")
        response.raise_for_status()
        user = response.json()["user"]
        tenant, permissions = user["tenant_id"], user["permissions"]
        if not isinstance(tenant, str) or not isinstance(permissions, list):
            raise ValueError("invalid identity projection")
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "observation_identity_unavailable") from exc
    return tenant, [p for p in permissions if isinstance(p, str)]


async def _bind_bearer_tenant(tenant_id: UUID, authorization: str) -> UUID:
    verified_tenant, permissions = await _bearer_identity(authorization)
    try:
        same_tenant = UUID(verified_tenant) == tenant_id
    except ValueError:
        same_tenant = False
    if not same_tenant or _OBSERVATION_PERMISSION not in permissions:
        raise HTTPException(403, "observation_access_denied")
    return tenant_id


async def _bind_observation_tenant(
    x_tenant_id: str, x_agent_token: str | None, authorization: str | None
) -> UUID:
    tenant_id = _parse_tenant(x_tenant_id)
    if x_agent_token is not None:
        expected = os.getenv("SAHOOL_AGENT_TOKEN", "")
        if not expected:
            raise HTTPException(503, "SAHOOL_AGENT_TOKEN is not configured")
        if not service_token_ok(x_agent_token, expected):
            raise HTTPException(401, "invalid service token")
        return tenant_id
    if authorization and authorization.startswith("Bearer "):
        return await _bind_bearer_tenant(tenant_id, authorization)
    raise HTTPException(401, "observations require a service token or bearer authorization")


# ── EXTRA-7: requested vs actual temporal extent ─────────────────────────────────────
#
# raster-service serves the latest bundle only. When the caller names a window, the
# actual acquisition is checked against it and a mismatch is refused — an October
# observation is never relabelled as the answer to a January request. Both extents are
# returned so the consumer can persist what it asked for next to what it received.
def _parse_window_date(name: str, value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError as exc:
        raise HTTPException(422, f"invalid {name}: expected YYYY-MM-DD") from exc


def _requested_extent(date_from: str | None, date_to: str | None) -> dict | None:
    start = _parse_window_date("date_from", date_from)
    end = _parse_window_date("date_to", date_to)
    if start and end and start > end:
        raise HTTPException(422, "date_from must not be after date_to")
    if start is None and end is None:
        return None
    return {
        "date_from": start.isoformat() if start else None,
        "date_to": end.isoformat() if end else None,
    }


def _actual_extent(acquired: list[datetime]) -> dict | None:
    if not acquired:
        return None
    return {"start": min(acquired).isoformat(), "end": max(acquired).isoformat()}


def _outside_requested(requested: dict | None, acquired: list[datetime]) -> bool:
    if requested is None:
        return False
    start, end = requested["date_from"], requested["date_to"]
    return any(
        (start is not None and item.date().isoformat() < start)
        or (end is not None and item.date().isoformat() > end)
        for item in acquired
    )


@app.get("/v1/fields/{field_id}/observations")
async def field_observations(
    field_id: str,
    x_tenant_id: Annotated[str, Header(alias="X-Tenant-Id")],
    season_id: Annotated[str, Query(min_length=1)],
    indicators: Annotated[str, Query()] = "ndvi",
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    x_agent_token: Annotated[str | None, Header(alias="X-Agent-Token")] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
):
    requested_extent = _requested_extent(date_from, date_to)
    tenant_id = await _bind_observation_tenant(x_tenant_id, x_agent_token, authorization)
    requested = [v.strip().lower() for v in indicators.split(",") if v.strip()]
    try:
        observations = await fetch_canonical_observations(
            field_id=field_id, tenant_id=tenant_id, season_id=season_id, indicators=requested
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(424, "canonical raster observation unavailable") from exc
    if not observations:
        raise HTTPException(424, "no consistent real canonical observation available")
    acquired = [item.acquired_at for item in observations]
    actual_extent = _actual_extent(acquired)
    if _outside_requested(requested_extent, acquired):
        raise HTTPException(
            424,
            {
                "code": "observation_outside_requested_window",
                "temporal_selection": "latest",
                "requested_temporal_extent": requested_extent,
                "actual_temporal_extent": actual_extent,
            },
        )
    return {
        "field_id": field_id,
        "season_id": season_id,
        "source": "indicators-service",
        "canonical": True,
        "temporal_selection": "latest",
        "requested_temporal_extent": requested_extent,
        "actual_temporal_extent": actual_extent,
        "observations": [item.model_dump(mode="json") for item in observations],
    }


@app.get("/v1/fields/{field_id}/observation-timeline")
async def observation_timeline(
    field_id: str,
    season_id: str = Query(..., min_length=1),
    indicators: str = Query("ndvi"),
    authorization: str | None = Header(None, alias="Authorization"),
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
):
    try:
        tenant_id = UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(400, "invalid X-Tenant-Id") from exc
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "season context requires bearer authorization")
    requested = [v.strip().lower() for v in indicators.split(",") if v.strip()]
    try:
        entries = await fetch_canonical_timeline(
            field_id=field_id,
            tenant_id=tenant_id,
            season_id=season_id,
            indicators=requested,
            authorization=authorization,
        )
    except TimelineSourceError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise HTTPException(
            status if status in {401, 403, 404} else 424, "canonical timeline source unavailable"
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(424, "canonical raster timeline unavailable") from exc
    latest = {}
    for item in entries:
        code = item.indicator.code
        if code not in latest and item.publication_status.value == "published":
            latest[code] = item.observation_ref
    return {
        "field_id": field_id,
        "season_id": season_id,
        "entries": [item.model_dump(mode="json") for item in entries],
        "latest_observation_refs": latest,
        "source": "indicators-service",
        "canonical": True,
        "supersession_projected": True,
        "evaluation_status": "available" if entries else "insufficient_history",
    }
