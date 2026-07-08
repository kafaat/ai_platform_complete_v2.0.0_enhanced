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


# P3.4 note: the per-tile / per-operation-plan RUNTIME counters (cache items, refreshed/fresh
# cache states, layer/operation breakdown) moved to weather-service along with the tile
# runtime. The platform observability SUBSYSTEM still counts the BFF endpoints that remain
# in-platform. `weather_action_recommendation` is exactly such an endpoint: it fetches its
# data via the operation-plan facade (converted → weather-service) and records a platform
# observation. We mock the facade so no live weather-service is needed, and assert the
# platform observability subsystem still counts the request.


def _canned_operation_plan(lat: float = 15.0, lon: float = 44.0) -> dict:
    """A weather-service-shaped operation-plan payload (what the facade would return)."""
    top = {
        "operation": "irrigation",
        "best": {
            "hour_offset": 3,
            "time": "+3h",
            "weather_time": "2026-07-08T15:00",
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
    return {
        "location": {"lat": lat, "lon": lon},
        "model": "best_match",
        "operations": [top],
        "recommended_now": [top],
        "top_recommendation": top,
        "source": "open-meteo+sahool-operation-plan",
        "partial": False,
        "upstream_errors": [],
    }


@pytest.mark.asyncio
async def test_observability_counts_action_recommendation(monkeypatch):
    from api.routers import weather

    for counter in weather._WEATHER_TILE_METRICS.values():
        counter.clear()

    async def fake_plan(lat, lon, *, operations, hours, model="best_match"):
        return _canned_operation_plan(lat, lon)

    monkeypatch.setattr(weather, "get_operation_plan", fake_plan)
    await weather.weather_action_recommendation(
        lat=15.0,
        lon=44.0,
        field_id="field-1",
        operations="irrigation,spraying",
        hours="0,3",
        model="best_match",
    )

    obs = weather.weather_observability()
    assert obs["metrics"]["requests"]["weather-action-recommendation"] == 1
    assert obs["metrics"]["cache_states"]["served"] == 1
