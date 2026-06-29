"""V12 — اختبارات خطة العمليات الزراعية المجمّعة لمحرك الطقس."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit


def _sample(**overrides):
    data = {
        "temperature_2m_c": 27.0,
        "relative_humidity_2m_pct": 54.0,
        "wind_speed_10m_kmh": 11.0,
        "wind_direction_10m_deg": 300.0,
        "wind_gusts_10m_kmh": 16.0,
        "precipitation_mm": 0.0,
        "cloud_cover_pct": 18.0,
        "pressure_msl_hpa": 1010.0,
        "vapour_pressure_deficit_kpa": 1.6,
        "et0_fao_evapotranspiration_mm": 4.8,
        "soil_temperature_6cm_c": 24.0,
        "soil_moisture_1_to_3cm_m3m3": 0.23,
    }
    data.update(overrides)
    return data


def test_parse_operations_csv_rejects_unknown_operation():
    from api.routers.weather import _parse_operations_csv

    with pytest.raises(HTTPException):
        _parse_operations_csv("spraying,plowing")


@pytest.mark.asyncio
async def test_operation_plan_ranks_irrigation_need(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()

    async def fake_fetch(lat, lon, time_key="now", model="best_match", **_kw):
        if time_key == "+3h":
            return _sample(vapour_pressure_deficit_kpa=2.8, soil_moisture_1_to_3cm_m3m3=0.16)
        return _sample(
            wind_speed_10m_kmh=24.0, wind_gusts_10m_kmh=36.0, vapour_pressure_deficit_kpa=2.6
        )

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_fetch)
    res = await weather.weather_operation_plan(
        15.0,
        44.0,
        operations="spraying,irrigation,harvesting,sowing",
        hours="0,3",
        model="best_match",
    )
    assert res["operations"][0]["operation"] == "irrigation"
    assert res["operations"][0]["priority"] >= 60
    assert any("VPD" in alert for alert in res["alerts_ar"])
    assert res["partial"] is False


@pytest.mark.asyncio
async def test_operation_plan_is_partial_when_some_frames_fail(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()

    async def fake_fetch(lat, lon, time_key="now", model="best_match", **_kw):
        if time_key == "+1h":
            raise RuntimeError("openmeteo temporary failure")
        return _sample()

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_fetch)
    res = await weather.weather_operation_plan(
        15.0,
        44.0,
        operations="spraying",
        hours="0,1,3",
        model="best_match",
    )
    assert res["partial"] is True
    assert res["operations"][0]["frames"]
    assert any("+1h" in err for err in res["upstream_errors"])
