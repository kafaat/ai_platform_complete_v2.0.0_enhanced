"""V21 — weather rate limiting + action/task/recommendation bridge tests."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit


def _sample(**overrides):
    data = {
        "temperature_2m_c": 33.0,
        "relative_humidity_2m_pct": 42.0,
        "wind_speed_10m_kmh": 11.0,
        "wind_direction_10m_deg": 300.0,
        "wind_gusts_10m_kmh": 15.0,
        "precipitation_mm": 0.0,
        "cloud_cover_pct": 8.0,
        "pressure_msl_hpa": 1009.0,
        "vapour_pressure_deficit_kpa": 2.7,
        "et0_fao_evapotranspiration_mm": 6.2,
        "soil_temperature_6cm_c": 29.0,
        "soil_moisture_1_to_3cm_m3m3": 0.14,
        "time": "2026-06-29T12:00:00Z",
    }
    data.update(overrides)
    return data


def test_weather_manifest_advertises_rate_limits_and_action_endpoints():
    from api.routers.weather import weather_layers_manifest

    manifest = weather_layers_manifest()
    assert "rate_limits" in manifest
    assert manifest["rate_limits"]["tile-data"]["limit"] > 0
    endpoints = set(manifest["decision_endpoints"])
    assert "/api/v1/weather/action-recommendation" in endpoints
    assert "/api/v1/weather/tasks/from-operation-plan" in endpoints
    assert "/api/v1/weather/recommendations/from-operation-plan" in endpoints


def test_weather_rate_limit_rejects_when_bucket_exhausted():
    from api.routers import weather

    weather._WEATHER_RATE_WINDOWS.clear()
    old = weather._WEATHER_RATE_LIMITS.get("unit-test")
    weather._WEATHER_RATE_LIMITS["unit-test"] = (1, 60)
    try:
        weather._enforce_weather_rate_limit(None, "unit-test")
        with pytest.raises(HTTPException) as exc:
            weather._enforce_weather_rate_limit(None, "unit-test")
        assert exc.value.status_code == 429
        assert weather._metrics_bucket("rate_limited")["unit-test"] == 1
    finally:
        if old is None:
            weather._WEATHER_RATE_LIMITS.pop("unit-test", None)
        else:
            weather._WEATHER_RATE_LIMITS["unit-test"] = old
        weather._WEATHER_RATE_WINDOWS.clear()


def test_build_weather_task_draft_maps_priority_and_notes():
    from api.routers import weather

    plan_item = {
        "operation": "irrigation",
        "priority": 92,
        "best": {
            "hour_offset": 3,
            "time": "+3h",
            "operation": {
                "operation": "irrigation",
                "score": 0.8,
                "suitability": "optimal",
                "limiting_factors": ["high_vpd_irrigation_need", "soil_moisture_low"],
            },
        },
        "advice_ar": "أولوية ري مرتفعة.",
    }
    draft = weather._build_weather_task_draft("field-1", plan_item)
    assert draft["field_id"] == "field-1"
    assert draft["task_type"] == "irrigation"
    assert draft["priority"] == 1
    assert draft["estimated_duration_min"] >= 60
    assert "Weather Operation Plan" in draft["notes"]


@pytest.mark.asyncio
async def test_weather_action_recommendation_returns_task_draft(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()

    async def fake_fetch(lat, lon, time_key="now", model="best_match", **_kw):
        return _sample()

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_fetch)
    result = await weather.weather_action_recommendation(
        lat=15.0,
        lon=45.0,
        field_id="field-1",
        operations="irrigation,spraying",
        hours="0,3",
        model="best_match",
    )
    assert result["field_id"] == "field-1"
    assert result["task_draft"]["field_id"] == "field-1"
    assert result["recommendation"]["recommendation_type"] == "weather_operation_plan"
    assert result["actions"]["create_task_endpoint"].endswith("tasks/from-operation-plan")
