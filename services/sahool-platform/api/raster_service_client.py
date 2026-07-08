"""Thin sahool-platform client for raster-service boundary calls.

P2 Raster Facade Cleanup:
- sahool-platform may verify tenant/RBAC and aggregate raster facts;
- raster-service owns raster computation/state;
- platform talks to raster-service through this small HTTP facade instead of
  open-coded ``httpx`` blocks in domain routers.

The helpers intentionally return raster JSON unchanged and do not fabricate
fallback values. HTTP errors are surfaced as FastAPI HTTPException with either
raster's JSON detail or a 502 service-unavailable envelope.
"""

from __future__ import annotations

import os
from typing import Any

# NOTE: fastapi is imported lazily inside the functions that raise/catch HTTPException.
# This module is reachable from the pure-logic `pytest -m unit` tier (imagery_automation ->
# raster_service_client import chain) which runs WITHOUT fastapi installed, so a module-level
# fastapi import would break test collection. Keep fastapi out of module import time.

DEFAULT_RASTER_SERVICE_URL = "http://sahool-raster-service:8001"


def raster_service_url() -> str:
    return os.getenv("RASTER_SERVICE_URL", DEFAULT_RASTER_SERVICE_URL).rstrip("/")


def raster_service_headers(*, tenant_id: str | None = None) -> dict[str, str]:
    headers = {"X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", "")}
    if tenant_id:
        headers["X-Tenant-Id"] = str(tenant_id)
    return headers


def _detail_from_response(resp: Any) -> Any:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001 - response may not be JSON
        return getattr(resp, "text", "raster-service returned an error")


async def raster_get_json(
    path: str,
    *,
    tenant_id: str | None = None,
    params: dict[str, Any] | None = None,
    timeout_s: float = 15.0,
) -> dict[str, Any]:
    """GET JSON from raster-service with service token + optional tenant header."""
    import httpx
    from fastapi import HTTPException

    url = f"{raster_service_url()}/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(
                url, params=params or {}, headers=raster_service_headers(tenant_id=tenant_id)
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"raster-service غير متاح: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=_detail_from_response(resp))
    data = resp.json()
    return data if isinstance(data, dict) else {"value": data}


async def raster_post_json(
    path: str,
    *,
    tenant_id: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """POST JSON to raster-service with service token + optional tenant header."""
    import httpx
    from fastapi import HTTPException

    url = f"{raster_service_url()}/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                url, json=payload or {}, headers=raster_service_headers(tenant_id=tenant_id)
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"raster-service غير متاح: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=_detail_from_response(resp))
    data = resp.json()
    return data if isinstance(data, dict) else {"value": data}


async def raster_get_raw(
    path: str,
    *,
    tenant_id: str | None = None,
    authorization: str | None = None,
    params: dict[str, Any] | None = None,
    timeout_s: float = 30.0,
) -> tuple[bytes, int, str | None, dict[str, str]]:
    """GET raw raster-service bytes for narrow compatibility passthroughs.

    This is intentionally generic only for legacy GET aliases such as
    `/api/raster/{path:path}` where the browser may request TileJSON or tile
    bytes. It centralizes raster URL, tenant promotion, and safe response header
    filtering so legacy routers do not open-code raster transport details.
    """
    import httpx
    from fastapi import HTTPException

    url = f"{raster_service_url()}/{path.lstrip('/')}"
    headers = raster_service_headers(tenant_id=tenant_id)
    if authorization:
        headers["Authorization"] = authorization
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(url, params=params or {}, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"raster-service غير متاح: {exc}") from exc

    forwarded_headers = {
        k: v
        for k, v in resp.headers.items()
        if k.lower() in {"cache-control", "etag", "last-modified"}
    }
    return resp.content, resp.status_code, resp.headers.get("content-type"), forwarded_headers


def raster_get_json_sync(
    path: str,
    *,
    tenant_id: str | None = None,
    params: dict[str, Any] | None = None,
    timeout_s: float = 15.0,
) -> dict[str, Any] | None:
    """Best-effort synchronous GET JSON from raster-service.

    Used by synchronous platform adapters. Unlike router-facing async helpers,
    this returns None on any failure so aggregate field-intelligence reads can
    honestly mark raster as unavailable without fabricating values.
    """
    try:
        import httpx
    except ImportError:
        return None

    url = f"{raster_service_url()}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.get(
                url, params=params or {}, headers=raster_service_headers(tenant_id=tenant_id)
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"value": data}
    except Exception:  # noqa: BLE001 - field-intelligence adapters are fail-soft
        return None


def get_provider_status_sync(*, timeout_s: float = 15.0) -> dict[str, Any] | None:
    """Return raster provider status for field-intelligence live context."""
    return raster_get_json_sync("/v1/providers/status", timeout_s=timeout_s)


def get_field_terrain_sync(
    field_id: str,
    *,
    tenant_id: str | None = None,
    timeout_s: float = 20.0,
) -> dict[str, Any] | None:
    """Return raster terrain summary for a field, fail-soft."""
    return raster_get_json_sync(
        f"/v1/fields/{field_id}/terrain",
        tenant_id=tenant_id,
        timeout_s=timeout_s,
    )


def get_indices_sync(
    field_id: str,
    *,
    lat: float,
    lon: float,
    timeout_s: float = 20.0,
) -> dict[str, Any] | None:
    """Return point/field index summary from raster-service /indices, fail-soft."""
    return raster_get_json_sync(
        "/indices",
        params={"field_id": field_id, "lat": lat, "lon": lon},
        timeout_s=timeout_s,
    )


async def get_available_dates(
    field_id: str,
    *,
    tenant_id: str,
    index: str | None = None,
    limit: int = 240,
) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": limit}
    if index:
        params["index"] = index
    return await raster_get_json(
        f"/v1/fields/{field_id}/available-dates",
        tenant_id=tenant_id,
        params=params,
        timeout_s=15.0,
    )


async def start_imagery_backfill(
    field_id: str,
    *,
    tenant_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return await raster_post_json(
        f"/v1/fields/{field_id}/imagery/backfill",
        tenant_id=tenant_id,
        payload=payload,
        timeout_s=60.0,
    )


async def get_imagery_backfill_status(
    field_id: str,
    run_id: int,
    *,
    tenant_id: str,
) -> dict[str, Any]:
    return await raster_get_json(
        f"/v1/fields/{field_id}/imagery/backfill/{run_id}",
        tenant_id=tenant_id,
        timeout_s=30.0,
    )


async def get_indicator_grid(
    field_id: str,
    *,
    tenant_id: str | None = None,
    index: str = "ndvi",
    date: str = "latest",
    timeout_s: float = 8.0,
) -> dict[str, Any]:
    return await raster_get_json(
        f"/v1/fields/{field_id}/indicator-grid",
        tenant_id=tenant_id,
        params={"index": index, "date": date},
        timeout_s=timeout_s,
    )


async def get_field_terrain(
    field_id: str,
    *,
    tenant_id: str,
    bbox: list[float] | tuple[float, ...] | None = None,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if bbox and len(bbox) == 4:
        params["bbox"] = ",".join(str(v) for v in bbox)
    return await raster_get_json(
        f"/v1/fields/{field_id}/terrain",
        tenant_id=tenant_id,
        params=params,
        timeout_s=timeout_s,
    )


async def process_field_cdse(
    field_id: str,
    *,
    tenant_id: str,
    payload: dict[str, Any],
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Queue CDSE-backed field processing in raster-service."""
    return await raster_post_json(
        f"/v1/fields/{field_id}/process-cdse",
        tenant_id=tenant_id,
        payload=payload,
        timeout_s=timeout_s,
    )


async def get_best_imagery_scene(
    *,
    bbox: list[float] | tuple[float, ...],
    lookback_days: int,
    max_cloud_pct: float,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Return raster-service /imagery/best response for a bbox."""
    return await raster_get_json(
        "/imagery/best",
        params={
            "west": bbox[0],
            "south": bbox[1],
            "east": bbox[2],
            "north": bbox[3],
            "lookback_days": lookback_days,
            "max_cloud_pct": max_cloud_pct,
        },
        timeout_s=timeout_s,
    )


async def search_imagery_scenes(
    *,
    bbox: list[float] | tuple[float, ...],
    datetime_start: str,
    datetime_end: str,
    limit: int = 5,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Search raster-service imagery catalog for scheduler-driven automation."""
    return await raster_post_json(
        "/imagery/search",
        payload={
            "bbox": list(bbox),
            "datetime_start": datetime_start,
            "datetime_end": datetime_end,
            "limit": limit,
        },
        timeout_s=timeout_s,
    )


async def process_field_from_stac(
    field_id: str,
    *,
    tenant_id: str,
    payload: dict[str, Any],
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Queue one indicator processing job from explicit STAC band hrefs."""
    return await raster_post_json(
        f"/v1/fields/{field_id}/process-from-stac",
        tenant_id=tenant_id,
        payload=payload,
        timeout_s=timeout_s,
    )


async def process_indicator_batch(
    *,
    tenant_id: str | None,
    payload: dict[str, Any],
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Queue raster-service batch indicator processing."""
    return await raster_post_json(
        "/process/batch",
        tenant_id=tenant_id,
        payload=payload,
        timeout_s=timeout_s,
    )


async def get_job_result(
    job_id: str,
    *,
    tenant_id: str | None = None,
    timeout_s: float = 10.0,
) -> dict[str, Any] | None:
    """Best-effort job result fetch; returns None when result is not ready."""
    from fastapi import HTTPException

    try:
        return await raster_get_json(
            f"/jobs/{job_id}/result",
            tenant_id=tenant_id,
            timeout_s=timeout_s,
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            return None
        raise
