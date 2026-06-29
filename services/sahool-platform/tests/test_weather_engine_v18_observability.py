"""V18 — اختبارات مراقبة/إحصائيات محرك الطقس."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _sample(**overrides):
    data = {
        "temperature_2m_c": 30.0,
        "relative_humidity_2m_pct": 50.0,
        "wind_speed_10m_kmh": 12.0,
        "wind_direction_10m_deg": 300.0,
        "wind_gusts_10m_kmh": 18.0,
        "precipitation_mm": 0.0,
        "cloud_cover_pct": 15.0,
        "pressure_msl_hpa": 1010.0,
        "vapour_pressure_deficit_kpa": 1.8,
        "et0_fao_evapotranspiration_mm": 5.0,
        "soil_temperature_6cm_c": 26.0,
        "soil_moisture_1_to_3cm_m3m3": 0.22,
    }
    data.update(overrides)
    return data


def test_weather_manifest_advertises_observability_endpoints():
    from api.routers.weather import weather_layers_manifest

    manifest = weather_layers_manifest()
    assert "/api/v1/weather/tile-cache/stats" in manifest["observability_endpoints"]
    assert "/api/v1/weather/observability" in manifest["observability_endpoints"]


@pytest.mark.asyncio
async def test_observability_counts_tile_requests(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()
    for counter in weather._WEATHER_TILE_METRICS.values():
        counter.clear()

    async def fake_fetch(lat, lon, time_key="now", model="best_match", **_kw):
        return _sample(temperature_2m_c=34.0)

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_fetch)
    await weather.weather_tile_data(5, 16, 14, layer="temperature", time="now", model="best_match")
    await weather.weather_tile_data(5, 16, 14, layer="temperature", time="now", model="best_match")

    obs = weather.weather_observability()
    assert obs["cache"]["items"] == 1
    assert obs["metrics"]["requests"]["tile-data"] == 2
    assert obs["metrics"]["layers"]["temperature"] == 2
    assert obs["metrics"]["cache_states"]["refreshed"] == 1
    assert obs["metrics"]["cache_states"]["fresh"] == 1


@pytest.mark.asyncio
async def test_observability_counts_operation_plan(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()
    for counter in weather._WEATHER_TILE_METRICS.values():
        counter.clear()

    async def fake_fetch(lat, lon, time_key="now", model="best_match", **_kw):
        return _sample(vapour_pressure_deficit_kpa=2.7, soil_moisture_1_to_3cm_m3m3=0.16)

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_fetch)
    await weather.weather_operation_plan(
        15.0, 44.0, operations="irrigation,spraying", hours="0,3", model="best_match"
    )

    obs = weather.weather_observability()
    assert obs["metrics"]["requests"]["operation-plan"] == 2
    assert obs["metrics"]["operations"]["irrigation"] == 1
    assert obs["metrics"]["operations"]["spraying"] == 1
