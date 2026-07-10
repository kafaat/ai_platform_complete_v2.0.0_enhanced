"""Thin sahool-platform client for weather-service boundary calls.

P3.4 Platform Weather Facade:
- weather-service owns provider calls, cache, tile math, wind grid, and operation scoring;
- sahool-platform may keep auth/rate-limit/BFF routes but must call this facade
  instead of importing Open-Meteo connectors or re-implementing weather runtime logic.
"""

from __future__ import annotations

import os
from typing import Any

# NOTE: fastapi is imported lazily inside the functions that raise/catch HTTPException.
# This module is reachable from the pure-logic `pytest -m unit` tier (via imagery/raster
# import chains) which runs WITHOUT fastapi installed, so a module-level fastapi import
# would break collection. Keep fastapi out of module import time.

DEFAULT_WEATHER_SERVICE_URL = "http://sahool-weather-service:8092"


def weather_service_url() -> str:
    return os.getenv("WEATHER_SERVICE_URL", DEFAULT_WEATHER_SERVICE_URL).rstrip("/")


def weather_service_headers(
    *, tenant_id: str | None = None, authorization: str | None = None
) -> dict[str, str]:
    headers = {"X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", "")}
    if tenant_id:
        headers["X-Tenant-Id"] = str(tenant_id)
    if authorization:
        headers["Authorization"] = authorization
    return headers


def _detail_from_response(resp: Any) -> Any:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return getattr(resp, "text", "weather-service returned an error")


async def weather_get_json(
    path: str,
    *,
    tenant_id: str | None = None,
    authorization: str | None = None,
    params: dict[str, Any] | None = None,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    """GET JSON from weather-service with service token + optional tenant/auth forwarding."""
    import httpx
    from fastapi import HTTPException

    url = f"{weather_service_url()}/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(
                url,
                params=params or {},
                headers=weather_service_headers(tenant_id=tenant_id, authorization=authorization),
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"weather-service غير متاح: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=_detail_from_response(resp))
    data = resp.json()
    return data if isinstance(data, dict) else {"value": data}


async def get_current_weather(
    lat: float, lon: float, *, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        "/v1/weather/current", params={"lat": lat, "lon": lon, "model": model}
    )


async def get_weather_forecast(
    lat: float, lon: float, *, days: int = 7, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        "/v1/weather/forecast", params={"lat": lat, "lon": lon, "days": days, "model": model}
    )


async def get_weather_historical(
    lat: float, lon: float, *, start_date: str, end_date: str
) -> dict[str, Any]:
    return await weather_get_json(
        "/v1/weather/historical",
        params={"lat": lat, "lon": lon, "start_date": start_date, "end_date": end_date},
    )


def _neutral_tile(z: int, x: int, y: int, *, layer: str) -> dict[str, Any]:
    """Neutral tile payload returned when weather-service is unreachable (502).

    Preserves the "don't flood the map with 502 per tile" guarantee across the
    platform->weather-service network hop: the map draws an empty/neutral tile
    instead of erroring on every request.
    """
    return {
        "tile": {"z": z, "x": x, "y": y},
        "layer": layer,
        "value": None,
        "sample": None,
        "available": False,
        "cache_state": "service_unavailable",
        "upstream_error": "weather-service unreachable",
        "rendered_by": "sahool-client-gridlayer",
    }


async def get_weather_tile_data(
    z: int,
    x: int,
    y: int,
    *,
    layer: str,
    time: str = "now",
    model: str = "best_match",
    interpolation: str = "center",
) -> dict[str, Any]:
    from fastapi import HTTPException

    try:
        return await weather_get_json(
            f"/v1/weather/tile-data/{z}/{x}/{y}",
            params={"layer": layer, "time": time, "model": model, "interpolation": interpolation},
        )
    except HTTPException as exc:
        if exc.status_code == 502:
            return _neutral_tile(z, x, y, layer=layer)
        raise


async def get_operation_tile_data(
    z: int,
    x: int,
    y: int,
    *,
    operation: str,
    time: str = "now",
    model: str = "best_match",
    interpolation: str = "center",
) -> dict[str, Any]:
    from fastapi import HTTPException

    try:
        return await weather_get_json(
            f"/v1/weather/operation-tile-data/{z}/{x}/{y}",
            params={
                "operation": operation,
                "time": time,
                "model": model,
                "interpolation": interpolation,
            },
        )
    except HTTPException as exc:
        if exc.status_code == 502:
            return _neutral_tile(z, x, y, layer=operation)
        raise


async def get_operation_window(
    lat: float, lon: float, *, operation: str, hours: str, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        "/v1/weather/operation-window",
        params={"lat": lat, "lon": lon, "operation": operation, "hours": hours, "model": model},
    )


async def get_operation_plan(
    lat: float, lon: float, *, operations: str, hours: str, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        "/v1/weather/operation-plan",
        params={"lat": lat, "lon": lon, "operations": operations, "hours": hours, "model": model},
    )


async def get_thermal_stress(
    lat: float,
    lon: float,
    *,
    crop: str | None = None,
    stage: str | None = None,
    days: int = 3,
    model: str = "best_match",
) -> dict[str, Any]:
    """منتج الإجهاد الحراريّ المركّب من weather-service (منطق الطقس يعيش هناك)."""
    params: dict[str, Any] = {"lat": lat, "lon": lon, "days": days, "model": model}
    if crop:
        params["crop"] = crop
    if stage:
        params["stage"] = stage
    return await weather_get_json("/v1/weather/thermal-stress", params=params)


async def get_lodging_risk(
    lat: float,
    lon: float,
    *,
    crop: str | None = None,
    stage: str | None = None,
    plant_height_cm: float | None = None,
    days: int = 3,
    model: str = "best_match",
) -> dict[str, Any]:
    """خطر الرقود من weather-service (منطق الطقس يعيش هناك)."""
    params: dict[str, Any] = {"lat": lat, "lon": lon, "days": days, "model": model}
    if crop:
        params["crop"] = crop
    if stage:
        params["stage"] = stage
    if plant_height_cm is not None:
        params["plant_height_cm"] = plant_height_cm
    return await weather_get_json("/v1/weather/lodging-risk", params=params)


async def get_pollination_risk(
    lat: float,
    lon: float,
    *,
    crop: str | None = None,
    stage: str | None = None,
    days: int = 3,
    model: str = "best_match",
) -> dict[str, Any]:
    """خطر الطقس على التلقيح من weather-service."""
    params: dict[str, Any] = {"lat": lat, "lon": lon, "days": days, "model": model}
    if crop:
        params["crop"] = crop
    if stage:
        params["stage"] = stage
    return await weather_get_json("/v1/weather/pollination-risk", params=params)


async def get_chill_accumulation(
    lat: float,
    lon: float,
    *,
    crop: str | None = None,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """تراكم البرودة الموسميّ من weather-service (نافذة تاريخيّة)."""
    params: dict[str, Any] = {
        "lat": lat,
        "lon": lon,
        "start_date": start_date,
        "end_date": end_date,
    }
    if crop:
        params["crop"] = crop
    return await weather_get_json("/v1/weather/chill-accumulation", params=params)


async def get_weather_tile_series(
    z: int, x: int, y: int, *, layer: str, hours: str, model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        f"/v1/weather/tile-series/{z}/{x}/{y}",
        params={"layer": layer, "hours": hours, "model": model},
    )


async def get_wind_grid(
    z: int, x: int, y: int, *, time: str = "now", model: str = "best_match"
) -> dict[str, Any]:
    return await weather_get_json(
        f"/v1/weather/wind-grid/{z}/{x}/{y}",
        params={"time": time, "model": model},
    )


async def get_tile_cache_stats() -> dict[str, Any]:
    return await weather_get_json("/v1/weather/tile-cache/stats")
