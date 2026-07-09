from __future__ import annotations

import os
import time
from typing import Any

import httpx

FORECAST_URL = os.getenv("OPEN_METEO_FORECAST_URL", "https://api.open-meteo.com/v1/forecast")
ARCHIVE_URL = os.getenv("OPEN_METEO_ARCHIVE_URL", "https://archive-api.open-meteo.com/v1/archive")
TIMEOUT_S = float(os.getenv("WEATHER_OPEN_METEO_TIMEOUT_S", "10"))
BREAKER_FAILURE_THRESHOLD = int(os.getenv("WEATHER_OPEN_METEO_BREAKER_FAILURES", "3"))
BREAKER_RESET_S = float(os.getenv("WEATHER_OPEN_METEO_BREAKER_RESET_S", "30"))
_BREAKER_FAILURES = 0
_BREAKER_OPEN_UNTIL = 0.0
_LAST_ERROR: str | None = None


def circuit_breaker_state() -> dict[str, Any]:
    remaining = max(0.0, _BREAKER_OPEN_UNTIL - time.monotonic())
    return {
        "provider": "open-meteo",
        "state": "open" if remaining > 0 else "closed",
        "failure_count": _BREAKER_FAILURES,
        "opens_after_failures": BREAKER_FAILURE_THRESHOLD,
        "reset_after_s": int(BREAKER_RESET_S),
        "open_remaining_s": round(remaining, 3),
        "last_error": _LAST_ERROR,
    }


def _record_success() -> None:
    global _BREAKER_FAILURES, _BREAKER_OPEN_UNTIL, _LAST_ERROR
    _BREAKER_FAILURES = 0
    _BREAKER_OPEN_UNTIL = 0.0
    _LAST_ERROR = None


def _record_failure(exc: Exception) -> None:
    global _BREAKER_FAILURES, _BREAKER_OPEN_UNTIL, _LAST_ERROR
    _BREAKER_FAILURES += 1
    _LAST_ERROR = str(exc)
    if _BREAKER_FAILURES >= BREAKER_FAILURE_THRESHOLD:
        _BREAKER_OPEN_UNTIL = time.monotonic() + BREAKER_RESET_S


def _as_list(payload: dict[str, Any], section: str, key: str) -> list[Any]:
    value = (payload.get(section) or {}).get(key)
    return value if isinstance(value, list) else []


def _at(values: list[Any], idx: int, default: Any = None) -> Any:
    if idx < 0 or idx >= len(values):
        return default
    value = values[idx]
    return default if value is None else value


async def _fetch_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    if _BREAKER_OPEN_UNTIL > time.monotonic():
        raise RuntimeError("Open-Meteo circuit breaker is open")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            _record_success()
            return data
    except Exception as exc:  # noqa: BLE001
        _record_failure(exc)
        raise


async def fetch_current(lat: float, lon: float, *, model: str = "best_match") -> dict[str, Any]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "weather_code",
                "cloud_cover",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "is_day",
                "surface_pressure",
            ]
        ),
        "hourly": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "et0_fao_evapotranspiration",
                "vapour_pressure_deficit",
                "soil_temperature_6cm",
                "soil_moisture_1_to_3cm",
                "cloud_cover",
                "surface_pressure",
            ]
        ),
        "forecast_days": 1,
        "timezone": "auto",
        "wind_speed_unit": "kmh",
    }
    if model and model not in {"best_match", "auto"}:
        params["models"] = model
    data = await _fetch_json(FORECAST_URL, params)
    current = data.get("current") or {}
    return normalize_current(current, lat=lat, lon=lon, source_payload=data)


def normalize_current(
    current: dict[str, Any], *, lat: float, lon: float, source_payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    source_payload = source_payload or {}
    wind_kmh = float(current.get("wind_speed_10m") or 0.0)
    gust_kmh = current.get("wind_gusts_10m")
    return {
        "location": {"lat": lat, "lon": lon},
        "temperature_c": current.get("temperature_2m"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "wind_speed_ms": round(wind_kmh / 3.6, 3),
        "wind_speed_10m_kmh": wind_kmh,
        "wind_direction_deg": current.get("wind_direction_10m"),
        "wind_direction_10m_deg": current.get("wind_direction_10m"),
        "wind_direction_source": "open-meteo",
        "wind_gusts_ms": round(float(gust_kmh) / 3.6, 3) if gust_kmh is not None else None,
        "wind_gusts_10m_kmh": gust_kmh,
        "precipitation_mm": current.get("precipitation") or 0,
        "cloud_cover_pct": current.get("cloud_cover"),
        "surface_pressure_hpa": current.get("surface_pressure"),
        "weather_code": current.get("weather_code"),
        "is_day": bool(current.get("is_day")) if current.get("is_day") is not None else None,
        "time": current.get("time"),
        "timestamp": current.get("time"),
        "source": "open-meteo",
        "timezone": source_payload.get("timezone"),
    }


async def fetch_forecast(
    lat: float, lon: float, *, days: int = 7, model: str = "best_match"
) -> dict[str, Any]:
    days = max(1, min(int(days or 7), 16))
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join(
            [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "et0_fao_evapotranspiration",
                "sunshine_duration",
                "wind_speed_10m_max",
                "sunrise",
                "sunset",
                "daylight_duration",
                "shortwave_radiation_sum",
            ]
        ),
        "forecast_days": days,
        "timezone": "auto",
        "wind_speed_unit": "kmh",
    }
    if model and model not in {"best_match", "auto"}:
        params["models"] = model
    data = await _fetch_json(FORECAST_URL, params)
    return normalize_daily(data, lat=lat, lon=lon, source="open-meteo", model=model)


async def fetch_historical(
    lat: float, lon: float, *, start_date: str, end_date: str
) -> dict[str, Any]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(
            [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "et0_fao_evapotranspiration",
                "wind_speed_10m_max",
            ]
        ),
        "timezone": "auto",
        "wind_speed_unit": "kmh",
    }
    data = await _fetch_json(ARCHIVE_URL, params)
    return normalize_daily(data, lat=lat, lon=lon, source="open-meteo-archive", model="ERA5")


def normalize_daily(
    data: dict[str, Any], *, lat: float, lon: float, source: str, model: str
) -> dict[str, Any]:
    daily = data.get("daily") or {}
    times = daily.get("time") if isinstance(daily.get("time"), list) else []
    days: list[dict[str, Any]] = []
    for idx, day in enumerate(times):
        sunshine_s = _at(_as_list(data, "daily", "sunshine_duration"), idx)
        daylight_s = _at(_as_list(data, "daily", "daylight_duration"), idx)
        wind_max_kmh = _at(_as_list(data, "daily", "wind_speed_10m_max"), idx, 0)
        days.append(
            {
                "date": day,
                "temp_max_c": _at(_as_list(data, "daily", "temperature_2m_max"), idx, 0),
                "temp_min_c": _at(_as_list(data, "daily", "temperature_2m_min"), idx, 0),
                "precipitation_mm": _at(_as_list(data, "daily", "precipitation_sum"), idx, 0),
                "et0_mm": _at(_as_list(data, "daily", "et0_fao_evapotranspiration"), idx),
                "sunshine_hours": round(float(sunshine_s) / 3600, 2)
                if sunshine_s is not None
                else None,
                "wind_max_ms": round(float(wind_max_kmh or 0) / 3.6, 3),
                "wind_max_kmh": wind_max_kmh,
                "weather_code": _at(_as_list(data, "daily", "weather_code"), idx),
                "sunrise": _at(_as_list(data, "daily", "sunrise"), idx),
                "sunset": _at(_as_list(data, "daily", "sunset"), idx),
                "daylight_hours": round(float(daylight_s) / 3600, 2)
                if daylight_s is not None
                else None,
                "solar_radiation_mj_m2": _at(
                    _as_list(data, "daily", "shortwave_radiation_sum"), idx
                ),
            }
        )
    return {
        "location": {"lat": lat, "lon": lon},
        "range": {"start": times[0] if times else None, "end": times[-1] if times else None},
        "days": days,
        "source": source,
        "model": model,
        "timezone": data.get("timezone"),
    }


async def fetch_tile_sample(
    lat: float, lon: float, *, time_key: str = "now", model: str = "best_match"
) -> dict[str, Any]:
    forecast_days = 3
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "cloud_cover",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "surface_pressure",
            ]
        ),
        "hourly": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "cloud_cover",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "et0_fao_evapotranspiration",
                "vapour_pressure_deficit",
                "soil_temperature_6cm",
                "soil_temperature_18cm",
                "soil_temperature_54cm",
                "soil_moisture_1_to_3cm",
                "soil_moisture_3_to_9cm",
                "surface_pressure",
            ]
        ),
        "forecast_days": forecast_days,
        "timezone": "auto",
        "wind_speed_unit": "kmh",
    }
    if model and model not in {"best_match", "auto"}:
        params["models"] = model
    data = await _fetch_json(FORECAST_URL, params)
    return normalize_tile_sample(data, lat=lat, lon=lon, time_key=time_key, model=model)


def _hour_offset(time_key: str) -> int:
    if time_key in {"now", "0", "+0h"}:
        return 0
    if time_key.startswith("+") and time_key.endswith("h"):
        try:
            return max(0, int(time_key[1:-1]))
        except ValueError:
            return 0
    return 0


def normalize_tile_sample(
    data: dict[str, Any], *, lat: float, lon: float, time_key: str, model: str
) -> dict[str, Any]:
    offset = _hour_offset(time_key)
    hourly = data.get("hourly") or {}
    current = data.get("current") or {}
    times = hourly.get("time") if isinstance(hourly.get("time"), list) else []
    idx = min(offset, max(0, len(times) - 1)) if times else 0
    if time_key == "now" and current:
        sample = normalize_current(current, lat=lat, lon=lon, source_payload=data)
        sample.update(
            {
                "et0_mm": None,
                "vpd_kpa": None,
                "soil_temperature_6cm_c": None,
                "soil_moisture_1_to_3cm_m3m3": None,
            }
        )
    else:
        wind = _at(hourly.get("wind_speed_10m") or [], idx, 0)
        gust = _at(hourly.get("wind_gusts_10m") or [], idx, wind)
        sample = {
            "location": {"lat": lat, "lon": lon},
            "temperature_c": _at(hourly.get("temperature_2m") or [], idx, 0),
            "humidity_pct": _at(hourly.get("relative_humidity_2m") or [], idx, 0),
            "precipitation_mm": _at(hourly.get("precipitation") or [], idx, 0),
            "cloud_cover_pct": _at(hourly.get("cloud_cover") or [], idx, 0),
            "wind_speed_10m_kmh": wind,
            "wind_speed_ms": round(float(wind or 0) / 3.6, 3),
            "wind_direction_10m_deg": _at(hourly.get("wind_direction_10m") or [], idx),
            "wind_direction_deg": _at(hourly.get("wind_direction_10m") or [], idx),
            "wind_direction_source": "open-meteo",
            "wind_gusts_10m_kmh": gust,
            "wind_gusts_ms": round(float(gust or 0) / 3.6, 3) if gust is not None else None,
            "et0_mm": _at(hourly.get("et0_fao_evapotranspiration") or [], idx),
            "vpd_kpa": _at(hourly.get("vapour_pressure_deficit") or [], idx),
            "soil_temperature_6cm_c": _at(hourly.get("soil_temperature_6cm") or [], idx),
            "soil_temperature_18cm_c": _at(hourly.get("soil_temperature_18cm") or [], idx),
            "soil_temperature_54cm_c": _at(hourly.get("soil_temperature_54cm") or [], idx),
            "soil_moisture_1_to_3cm_m3m3": _at(hourly.get("soil_moisture_1_to_3cm") or [], idx),
            "soil_moisture_3_to_9cm_m3m3": _at(hourly.get("soil_moisture_3_to_9cm") or [], idx),
            "surface_pressure_hpa": _at(hourly.get("surface_pressure") or [], idx),
            "time": _at(times, idx),
            "timestamp": _at(times, idx),
            "source": "open-meteo",
        }
    sample["model"] = model
    sample["time_key"] = time_key
    return sample


async def readiness_probe(lat: float = 15.3694, lon: float = 44.1910) -> dict[str, Any]:
    """Small upstream probe used by /readyz.

    It intentionally reuses the real provider adapter so readiness reflects the same
    path used by current/forecast/tile calls. Operators can keep the platform alive
    with degraded status while the circuit breaker protects Open-Meteo from storms.
    """
    try:
        data = await fetch_current(lat, lon, model="best_match")
        return {
            "ok": True,
            "provider": "open-meteo",
            "time": data.get("time"),
            "circuit_breaker": circuit_breaker_state(),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "provider": "open-meteo",
            "error": str(exc),
            "circuit_breaker": circuit_breaker_state(),
        }
