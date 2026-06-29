"""V19 — Prometheus metrics + cache prune tests for weather engine."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _sample(**overrides):
    data = {
        "temperature_2m_c": 31.0,
        "relative_humidity_2m_pct": 52.0,
        "wind_speed_10m_kmh": 14.0,
        "wind_direction_10m_deg": 315.0,
        "wind_gusts_10m_kmh": 20.0,
        "precipitation_mm": 0.0,
        "cloud_cover_pct": 12.0,
        "pressure_msl_hpa": 1011.0,
        "vapour_pressure_deficit_kpa": 2.1,
        "et0_fao_evapotranspiration_mm": 5.8,
        "soil_temperature_6cm_c": 27.0,
        "soil_moisture_1_to_3cm_m3m3": 0.21,
    }
    data.update(overrides)
    return data


def test_weather_manifest_advertises_prometheus_and_prune_endpoints():
    from api.routers.weather import weather_layers_manifest

    manifest = weather_layers_manifest()
    endpoints = set(manifest["observability_endpoints"])
    assert "/api/v1/weather/metrics.prom" in endpoints
    assert "/api/v1/weather/tile-cache/prune" in endpoints


@pytest.mark.asyncio
async def test_prometheus_metrics_contains_weather_counters(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()
    for counter in weather._WEATHER_TILE_METRICS.values():
        counter.clear()

    async def fake_fetch(lat, lon, time_key="now", model="best_match", **_kw):
        return _sample(temperature_2m_c=35.0)

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_fetch)
    await weather.weather_tile_data(5, 16, 14, layer="temperature", time="now", model="best_match")

    response = weather.weather_metrics_prometheus()
    body = response.body.decode("utf-8")
    assert "# TYPE sahool_weather_requests_total counter" in body
    assert 'sahool_weather_requests_total{endpoint="tile-data"} 1' in body
    assert 'sahool_weather_layers_total{layer="temperature"} 1' in body
    assert 'sahool_weather_cache_items{state="total"} 1' in body


def test_weather_cache_prune_removes_expired_only():
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()
    now = weather.monotonic()
    weather._WEATHER_TILE_CACHE["fresh"] = (now - 5, _sample())
    weather._WEATHER_TILE_CACHE["stale"] = (
        now - weather._WEATHER_TILE_CACHE_TTL_S - 5,
        _sample(temperature_2m_c=29.0),
    )
    weather._WEATHER_TILE_CACHE["expired"] = (
        now - weather._WEATHER_TILE_STALE_TTL_S - 5,
        _sample(temperature_2m_c=20.0),
    )

    result = weather.weather_tile_cache_prune(expired_only=True)
    assert result["before"] == 3
    assert result["removed"] == 1
    assert result["after"] == 2
    assert "expired" not in weather._WEATHER_TILE_CACHE
    assert "fresh" in weather._WEATHER_TILE_CACHE
    assert "stale" in weather._WEATHER_TILE_CACHE


def test_weather_cache_prune_can_remove_stale_items():
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()
    now = weather.monotonic()
    weather._WEATHER_TILE_CACHE["fresh"] = (now - 5, _sample())
    weather._WEATHER_TILE_CACHE["stale"] = (
        now - weather._WEATHER_TILE_CACHE_TTL_S - 5,
        _sample(temperature_2m_c=29.0),
    )

    result = weather.weather_tile_cache_prune(expired_only=False)
    assert result["removed"] == 1
    assert result["after"] == 1
    assert "fresh" in weather._WEATHER_TILE_CACHE
    assert "stale" not in weather._WEATHER_TILE_CACHE
