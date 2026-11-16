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
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Response

_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))
import observation_runtime  # noqa: E402
import observation_store  # noqa: E402
from observation_runtime import canonicalize_bundle, fetch_canonical_observations  # noqa: E402
from observation_timeline import (  # noqa: E402
    SOURCE_FALLBACK,
    TimelineSourceError,
    fetch_canonical_timeline,
    source_label,
)

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
            "canonical_observation_store": True,
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
            "/internal/v1/observations",
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
    observation_runtime.LAST_BUNDLE.set(None)
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
    observations, source, store_status = await _bind_stored_observations(
        observations, observation_runtime.LAST_BUNDLE.get(), field_id, tenant_id, season_id
    )
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
        "observation_source": source,
        "store_status": store_status,
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
    sources: dict[str, str] = {}

    async def _bind_stored(indicator: str, start: datetime, end: datetime, points: list):
        # The season window is inclusive by calendar day, as for the raster points.
        rows = await observation_store.observations_between(
            tenant_id=tenant_id,
            field_id=field_id,
            indicator=indicator,
            start=datetime.combine(start.date(), time.min, UTC),
            end=datetime.combine(end.date() + timedelta(days=1), time.min, UTC),
        )
        if not rows:
            return points, 0
        return observation_store.merge_timeline_points(
            points, rows, tenant_id=tenant_id, field_id=field_id, indicator=indicator
        )

    try:
        entries = await fetch_canonical_timeline(
            field_id=field_id,
            tenant_id=tenant_id,
            season_id=season_id,
            indicators=requested,
            authorization=authorization,
            bind_stored=_bind_stored if observation_store.configured() else None,
            sources=sources,
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
        "observation_sources": sources,
        "supersession_projected": True,
        "evaluation_status": "available" if entries else "insufficient_history",
    }


# ── W1-11: the canonical observation store (owner decision 2026-11-16) ─────────────────────
#
# raster-service pushes every published product here (``POST /internal/v1/observations``). The
# two read routes above still ask raster-service which product is current (its asset lifecycle
# drops a stale geometry or a superseded reprocess), then serve the stored fact of exactly that
# product; a product with no stored row is served from the computed path (``observation_source``).
async def _bind_stored_observations(
    computed: list, bundle: dict | None, field_id: str, tenant_id: UUID, season_id: str
) -> tuple[list, str, str]:
    """Replace each computed observation by the stored row of the same asset and revision.

    Returns ``(observations, observation_source, store_status)``. The computed observations are
    kept as they are when the store is not configured, cannot answer, or holds no row of the
    product raster-service serves now.
    """
    if not observation_store.configured():
        return computed, SOURCE_FALLBACK, "not_configured"
    items = (bundle or {}).get("observations") or {}
    if not items:
        return computed, SOURCE_FALLBACK, "unbound"
    prefix = "urn:sahool:raster-asset:"
    ids = sorted({str(obs.asset_ref).removeprefix(prefix) for obs in computed})
    rows = await observation_store.observations_for_assets(
        tenant_id=tenant_id, field_id=field_id, observation_ids=ids
    )
    if rows is None:
        return computed, SOURCE_FALLBACK, "unavailable"
    bound = []
    stored = 0
    for obs in computed:
        code = obs.indicator.code
        item = items.get(code)
        row = None
        if isinstance(item, dict):
            row = observation_store.match_bundle_item(
                rows,
                observation_id=str(obs.asset_ref).removeprefix(prefix),
                identity=observation_store.bundle_item_identity(item, bundle or {}),
            )
        if row is None:
            bound.append(obs)
            continue
        bound.extend(
            canonicalize_bundle(
                bundle={
                    "field_id": field_id,
                    "observations": {code: observation_store.bundle_item(row)},
                },
                tenant_id=tenant_id,
                season_id=season_id,
                published_at=row["published_at"],
            )
        )
        stored += 1
    status = "served" if stored == len(computed) else ("partial" if stored else "not_stored")
    return bound, source_label(len(computed), stored), status


def _require_service_caller(x_agent_token: str | None) -> None:
    expected = os.getenv("SAHOOL_AGENT_TOKEN", "")
    if not expected:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN is not configured")
    if not service_token_ok(x_agent_token, expected):
        raise HTTPException(401, "invalid service token")


@app.post("/internal/v1/observations")
async def ingest_published_observation(
    body: observation_store.PublishedObservationV1,
    response: Response,
    x_tenant_id: Annotated[str, Header(alias="X-Tenant-Id")],
    x_agent_token: Annotated[str | None, Header(alias="X-Agent-Token")] = None,
):
    """Store one observation raster-service published (service-to-service only).

    The caller proves the mesh service token and asserts the tenant in ``X-Tenant-Id``; a body
    for another tenant is refused. 201 created · 200 replay of the same content · 409 the same
    observation id and product revision with other content (nothing stored) · 503 the store
    cannot answer. A new geometry revision or algorithm version of the same scene is a new row.

    Trust: the shared mesh token (OI-01), like every internal route of the mesh. A stored row is
    served only for the product raster-service itself still publishes at the same revision, so
    a row that matches no raster product is never read; correcting a stored row is a reviewed
    schema-owner action (v286 header).
    """
    _require_service_caller(x_agent_token)
    tenant_id = _parse_tenant(x_tenant_id)
    if body.tenant_id != tenant_id:
        raise HTTPException(403, "tenant_mismatch")
    try:
        result = await observation_store.insert_observation(body)
    except observation_store.StoreUnavailable as exc:
        raise HTTPException(503, "canonical observation store unavailable") from exc
    if result["status"] == "conflict":
        raise HTTPException(
            409,
            {
                "code": "observation_conflict",
                "observation_id": result["observation_id"],
                "revision_key": result.get("revision_key"),
                "stored_payload_sha256": result["stored_payload_sha256"],
                "offered_payload_sha256": result["payload_sha256"],
            },
        )
    response.status_code = 201 if result["status"] == "created" else 200
    return {
        "status": result["status"],
        "observation_id": result["observation_id"],
        "revision_key": result.get("revision_key"),
        "asset_ref": f"urn:sahool:raster-asset:{result['observation_id']}",
        "payload_sha256": result["payload_sha256"],
        "published_at": result["published_at"].isoformat()
        if isinstance(result["published_at"], datetime)
        else result["published_at"],
    }
