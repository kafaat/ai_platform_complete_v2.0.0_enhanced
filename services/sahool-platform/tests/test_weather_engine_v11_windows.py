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


# NOTE (P3.4): operation-window best-frame selection and tile-series partial handling moved
# to weather-service (platform routes are now thin facades to it). The equivalent runtime
# tests now live in services/weather-service/tests/test_p3_4_weather_service_runtime_coverage.py.
# The field-weather-summary endpoint below is still composed in-platform (it derives alerts
# and operations locally), so its test stays here.


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
