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
    # P3.4: the tile runtime (and its per-tile request/layer/cache counters) moved to
    # weather-service. The platform Prometheus EXPORT is still a platform concern: it renders
    # counters for the BFF endpoints that remain in-platform. We drive a remaining local
    # endpoint (action-recommendation) whose data comes via the operation-plan facade
    # (mocked, no live weather-service), then assert the exporter renders the counter.
    from api.routers import weather

    for counter in weather._WEATHER_TILE_METRICS.values():
        counter.clear()

    top = {
        "operation": "irrigation",
        "best": {
            "hour_offset": 3,
            "time": "+3h",
            "operation": {
                "operation": "irrigation",
                "score": 0.82,
                "suitability": "optimal",
                "limiting_factors": ["soil_moisture_low"],
            },
        },
        "frames": [],
        "recommended": True,
        "priority": 0.82,
        "advice_ar": "أولوية ريّ مرتفعة.",
    }

    async def fake_plan(lat, lon, *, operations, hours, model="best_match"):
        return {
            "location": {"lat": lat, "lon": lon},
            "model": model,
            "operations": [top],
            "recommended_now": [top],
            "top_recommendation": top,
            "source": "open-meteo+sahool-operation-plan",
            "partial": False,
            "upstream_errors": [],
        }

    monkeypatch.setattr(weather, "get_operation_plan", fake_plan)
    await weather.weather_action_recommendation(
        lat=15.0, lon=44.0, field_id="field-1", operations="irrigation", hours="0,3"
    )

    response = weather.weather_metrics_prometheus()
    body = response.body.decode("utf-8")
    assert "# TYPE sahool_weather_requests_total counter" in body
    assert 'sahool_weather_requests_total{endpoint="weather-action-recommendation"} 1' in body
    assert "# TYPE sahool_weather_cache_items gauge" in body
    assert 'sahool_weather_cache_items{state="total"}' in body


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
