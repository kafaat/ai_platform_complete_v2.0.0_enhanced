from __future__ import annotations

import sys
from typing import Literal

from cache import get as cache_get
from cache import set as cache_set
from cache import stats as cache_stats
from fastapi import HTTPException, Query
from open_meteo import circuit_breaker_state, fetch_current, fetch_forecast, fetch_historical, fetch_tile_sample, readiness_probe
from operations import advice_ar, best_operation_frame, operation_suitability
from tiles import (
    ALLOWED_LAYERS,
    derived_layer_value,
    parse_series_hours,
    tile_center,
    tile_interpolation_points,
    time_key_from_hour,
    unit_for_layer,
    validate_time_model,
)




def _facade_attr(name: str):
    """Resolve monkeypatch-compatible runtime hooks from the public main module.

Legacy tests and operators patch ``main.fetch_*`` directly. After P2 extraction the
real implementation lives here, so route handlers resolve patchable hooks through
``sys.modules['main']`` when available, falling back to local imports.
"""
    facade = sys.modules.get("main")
    if facade is not None and hasattr(facade, name):
        return getattr(facade, name)
    return globals()[name]


def healthz():
    return {"status": "ok", "service": "weather-service", "mode": "runtime"}


def health():
    # Backward-compatible health alias for older local scripts; real readiness stays /readyz.
    return healthz()


async def readyz():
    upstream = await _facade_attr("readiness_probe")()
    cache = cache_stats()
    status = "ready" if upstream.get("ok") else "degraded"
    return {
        "status": status,
        "service": "weather-service",
        "mode": "runtime",
        "implemented_runtime": True,
        "upstream_open_meteo": upstream,
        "cache": cache,
        "circuit_breaker": circuit_breaker_state(),
    }


def root():
    return {
        "service": "weather-service",
        "mode": "runtime",
        "implemented_runtime": True,
        "note_ar": "خدمة الطقس الفعلية: Open-Meteo core + operation windows + tiles/wind grid.",
    }


def contract():
    return {
        "service": "weather-service",
        "contract_version": "2026-07-09.runtime",
        "implemented_runtime": True,
        "mode": "runtime",
        "ownership": "target-weather-system-of-record",
        "capabilities": {
            "p3_1_core": ["current-weather", "forecast", "historical-weather", "cache"],
            "p3_2_operation_windows": ["operation-window", "operation-plan", "operation-tile-data"],
            "p3_3_tiles_wind_grid": ["tile-data", "tile-series", "wind-grid", "tile-interpolation"],
        },
        "source": "open-meteo+sahool-rules",
    }


async def current_weather(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    model: str = "best_match",
):
    try:
        return await _facade_attr("fetch_current")(lat, lon, model=model)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo current: {exc}") from exc


async def forecast_weather(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    days: int = 7,
    model: str = "best_match",
):
    try:
        return await _facade_attr("fetch_forecast")(lat, lon, days=days, model=model)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo forecast: {exc}") from exc


async def historical_weather(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    start_date: str = Query(...),
    end_date: str = Query(...),
):
    try:
        return await _facade_attr("fetch_historical")(lat, lon, start_date=start_date, end_date=end_date)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo historical: {exc}") from exc


async def _cached_sample(lat: float, lon: float, time: str, model: str, key_prefix: str = "sample"):
    time, model = validate_time_model(time, model)
    key = f"{key_prefix}:{round(lat, 4)}:{round(lon, 4)}:{time}:{model}"
    sample, state, age = cache_get(key)
    upstream_error = None
    if state != "fresh":
        try:
            sample = await _facade_attr("fetch_tile_sample")(lat, lon, time_key=time, model=model)
            cache_set(key, sample)
            return sample, "refreshed", 0, None
        except Exception as exc:
            upstream_error = str(exc)
            if sample is not None and state == "stale":
                return sample, "stale_fallback", age, upstream_error
            raise
    return sample, state, age, upstream_error


async def operation_window(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    operation: Literal[
        "spraying", "harvesting", "sowing", "fertilizing", "irrigation"
    ] = "spraying",
    hours: str = "0,1,3,6,12,24,48",
    model: str = "best_match",
):
    frames = []
    upstream_errors: list[str] = []
    _, model = validate_time_model("now", model)
    for h in parse_series_hours(hours):
        t = time_key_from_hour(h)
        try:
            sample, cache_state, cache_age_s, upstream_error = await _cached_sample(
                lat, lon, t, model, f"window:{operation}"
            )
            decision = operation_suitability(sample, operation)
            frames.append(
                {
                    "hour_offset": h,
                    "time": t,
                    "weather_time": sample.get("time"),
                    "operation": decision,
                    "sample": sample,
                    "cache_state": cache_state,
                    "cache_age_s": cache_age_s,
                    "upstream_error": upstream_error,
                }
            )
        except Exception as exc:
            upstream_errors.append(f"{t}: {exc}")
    if not frames:
        raise HTTPException(status_code=502, detail="Open-Meteo operation-window unavailable")
    best = best_operation_frame(frames)
    return {
        "location": {"lat": lat, "lon": lon},
        "operation": operation,
        "model": model,
        "frames": frames,
        "best": best,
        "advice_ar": advice_ar(best.get("operation") if best else None),
        "source": "open-meteo+sahool-rules",
        "partial": bool(upstream_errors),
        "upstream_errors": upstream_errors[:6],
    }


async def operation_plan(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    operations: str = "spraying,irrigation,harvesting,sowing",
    hours: str = "0,1,3,6,12,24,48",
    model: str = "best_match",
):
    items = []
    errors: list[str] = []
    for op in [x.strip() for x in operations.split(",") if x.strip()]:
        try:
            window = await operation_window(
                lat=lat, lon=lon, operation=op, hours=hours, model=model
            )  # type: ignore[arg-type]
            best = window.get("best")
            items.append(
                {
                    "operation": op,
                    "best": best,
                    "frames": window.get("frames", []),
                    "recommended": bool(
                        best and (best.get("operation") or {}).get("score", 0) >= 0.55
                    ),
                    "priority": (best.get("operation") or {}).get("score", 0) if best else 0,
                    "advice_ar": window.get("advice_ar"),
                }
            )
        except Exception as exc:
            errors.append(f"{op}: {exc}")
    items.sort(key=lambda item: item.get("priority", 0), reverse=True)
    if not items:
        raise HTTPException(status_code=502, detail="Open-Meteo operation-plan unavailable")
    return {
        "location": {"lat": lat, "lon": lon},
        "model": model,
        "operations": items,
        "recommended_now": [i for i in items if i.get("recommended")],
        "top_recommendation": items[0] if items else None,
        "source": "open-meteo+sahool-operation-plan",
        "partial": bool(errors),
        "upstream_errors": errors[:10],
    }


async def tile_data(
    z: int,
    x: int,
    y: int,
    layer: str = "temperature",
    time: str = "now",
    model: str = "best_match",
    interpolation: Literal["center", "grid"] = "center",
):
    if z < 0 or z > 18:
        raise HTTPException(status_code=400, detail="z outside 0..18")
    if x < 0 or y < 0 or x >= 2**z or y >= 2**z:
        raise HTTPException(status_code=400, detail="x/y outside tile range")
    if layer not in ALLOWED_LAYERS:
        raise HTTPException(status_code=400, detail=f"unsupported layer: {layer}")
    time, model = validate_time_model(time, model)
    lat, lon = tile_center(z, x, y)
    interpolation_payload = None
    # Neutral-tile guarantee: a total upstream failure with no cache must NOT 500/flood
    # the map with errors per tile. Return a neutral tile (value=null, 200) instead —
    # honest "unavailable" state, not a fabricated value. (Stale cache still wins via
    # _cached_sample's own stale_fallback path.)
    try:
        sample, cache_state, cache_age_s, upstream_error = await _cached_sample(
            lat, lon, time, model, f"tile:{z}:{x}:{y}"
        )
    except Exception as exc:  # noqa: BLE001 — upstream down + no cache ⇒ neutral tile
        sample, cache_state, cache_age_s, upstream_error = None, "unavailable", 0, str(exc)
    if interpolation == "grid":
        points = []
        for pt in tile_interpolation_points(z, x, y):
            try:
                s, state, age, err = await _cached_sample(
                    pt["lat"], pt["lon"], time, model, f"tile-grid:{z}:{x}:{y}:{pt['name']}"
                )
                points.append(
                    {
                        **pt,
                        "value": derived_layer_value(layer, s),
                        "sample": s,
                        "cache_state": state,
                        "cache_age_s": age,
                        "upstream_error": err,
                    }
                )
            except Exception as exc:
                points.append({**pt, "value": None, "error": str(exc)})
        interpolation_payload = {"mode": "grid", "points": points}
    return {
        "tile": {"z": z, "x": x, "y": y},
        "center": {"lat": lat, "lon": lon},
        "layer": layer,
        "value": derived_layer_value(layer, sample),
        "unit": unit_for_layer(layer),
        "sample": sample,
        "time": time,
        "model": model,
        "source": "open-meteo+sahool-rules",
        "rendered_by": "sahool-client-gridlayer",
        "cache_state": cache_state,
        "cache_age_s": cache_age_s,
        "upstream_error": upstream_error,
        "interpolation": interpolation_payload,
    }


async def operation_tile_data(
    z: int,
    x: int,
    y: int,
    operation: Literal[
        "spraying", "harvesting", "sowing", "fertilizing", "irrigation"
    ] = "spraying",
    time: str = "now",
    model: str = "best_match",
    interpolation: Literal["center", "grid"] = "center",
):
    payload = await tile_data(
        z=z, x=x, y=y, layer="temperature", time=time, model=model, interpolation=interpolation
    )
    decision = operation_suitability(payload["sample"], operation)
    payload.update(
        {
            "layer": f"operation_{operation}",
            "value": decision["score"],
            "unit": "score",
            "operation": decision,
            "source": "open-meteo+sahool-rules",
        }
    )
    return payload


async def tile_series(
    z: int,
    x: int,
    y: int,
    layer: str = "precipitation",
    hours: str = "0,1,3,6,12,24,48",
    model: str = "best_match",
):
    frames = []
    errors: list[str] = []
    for h in parse_series_hours(hours):
        t = time_key_from_hour(h)
        try:
            payload = await tile_data(z=z, x=x, y=y, layer=layer, time=t, model=model)
            frames.append(
                {
                    "hour_offset": h,
                    "time": t,
                    "weather_time": payload.get("sample", {}).get("time"),
                    "value": payload.get("value"),
                    "sample": payload.get("sample"),
                    "cache_state": payload.get("cache_state"),
                    "cache_age_s": payload.get("cache_age_s"),
                    "upstream_error": payload.get("upstream_error"),
                }
            )
        except Exception as exc:
            errors.append(f"{t}: {exc}")
    if not frames:
        raise HTTPException(status_code=502, detail="Open-Meteo tile-series unavailable")
    lat, lon = tile_center(z, x, y)
    return {
        "tile": {"z": z, "x": x, "y": y},
        "center": {"lat": lat, "lon": lon},
        "layer": layer,
        "frames": frames,
        "model": model,
        "source": "open-meteo",
        "rendered_by": "sahool-client-gridlayer",
        "partial": bool(errors),
        "upstream_errors": errors[:6],
    }


async def wind_grid(z: int, x: int, y: int, time: str = "now", model: str = "best_match"):
    payload = await tile_data(
        z=z, x=x, y=y, layer="wind", time=time, model=model, interpolation="grid"
    )
    return {**payload, "layer": "wind", "wind_grid": payload.get("interpolation")}


def tile_cache_stats():
    return cache_stats()
