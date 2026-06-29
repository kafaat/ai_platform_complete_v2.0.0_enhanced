"""V11 — اختبارات نوافذ العمليات والسلاسل الزمنية لمحرك الطقس."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _sample(**overrides):
    data = {
        "temperature_2m_c": 24.0,
        "relative_humidity_2m_pct": 58.0,
        "wind_speed_10m_kmh": 10.0,
        "wind_direction_10m_deg": 300.0,
        "wind_gusts_10m_kmh": 16.0,
        "precipitation_mm": 0.0,
        "cloud_cover_pct": 22.0,
        "pressure_msl_hpa": 1012.0,
        "vapour_pressure_deficit_kpa": 1.4,
        "et0_fao_evapotranspiration_mm": 4.2,
        "soil_temperature_6cm_c": 22.0,
        "soil_moisture_1_to_3cm_m3m3": 0.24,
    }
    data.update(overrides)
    return data


@pytest.mark.asyncio
async def test_operation_window_selects_best_future_frame(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()

    async def fake_fetch(lat, lon, time_key="now", model="best_match", **_kw):
        if time_key == "now":
            return _sample(wind_speed_10m_kmh=31.0, wind_gusts_10m_kmh=42.0, precipitation_mm=1.0)
        if time_key == "+3h":
            return _sample(wind_speed_10m_kmh=9.0, wind_gusts_10m_kmh=12.0, precipitation_mm=0.0)
        return _sample(wind_speed_10m_kmh=18.0, wind_gusts_10m_kmh=22.0, precipitation_mm=0.0)

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_fetch)
    res = await weather.weather_operation_window(
        15.0, 44.0, operation="spraying", hours="0,3,6", model="best_match"
    )
    assert res["best"]["time"] == "+3h"
    assert res["best"]["operation"]["suitability"] in {"optimal", "acceptable"}
    assert res["frames"][0]["operation"]["suitability"] == "unsafe"
    assert res["partial"] is False


@pytest.mark.asyncio
async def test_tile_series_is_partial_when_one_frame_fails(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()

    async def fake_fetch(lat, lon, time_key="now", model="best_match", **_kw):
        if time_key == "+3h":
            raise RuntimeError("one frame failed")
        return _sample(precipitation_mm=0.4 if time_key == "+1h" else 0.0)

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_fetch)
    res = await weather.weather_tile_series(
        5, 16, 14, layer="precipitation", hours="0,1,3", model="best_match"
    )
    assert len(res["frames"]) == 2
    assert res["partial"] is True
    assert any("+3h" in e for e in res["upstream_errors"])


@pytest.mark.asyncio
async def test_field_weather_summary_returns_operations_and_alerts(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()

    async def fake_fetch(*_args, **_kwargs):
        return _sample(wind_speed_10m_kmh=25.0, vapour_pressure_deficit_kpa=2.7)

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_fetch)
    res = await weather.weather_field_summary(15.0, 44.0, time="now", model="best_match")
    assert {"spraying", "irrigation", "harvesting", "sowing"} <= set(res["operations"])
    assert any("رياح" in a for a in res["alerts_ar"])
    assert any("VPD" in a for a in res["alerts_ar"])
