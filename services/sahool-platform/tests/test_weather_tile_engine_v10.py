"""V10 — اختبارات محرك بلاطات Open‑Meteo/SAHOOL بدون شبكة.

تغطي: manifest، validation، cache fresh، stale fallback، وقرارات العمليات.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

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


def test_weather_layers_manifest_contains_agronomic_layers():
    from api.routers.weather import weather_layers_manifest

    m = weather_layers_manifest()
    layer_keys = {lyr["key"] for lyr in m["layers"]}
    op_keys = {lyr["key"] for lyr in m["operation_layers"]}
    assert {"et0", "vpd", "soil_moisture", "soil_temperature"} <= layer_keys
    assert {
        "operation_spraying",
        "operation_irrigation",
        "operation_harvesting",
        "operation_sowing",
    } <= op_keys
    assert m["source"] == "open-meteo"
    assert m["rendered_by"] == "sahool"
    assert m["cache"]["stale_ttl_s"] > m["cache"]["ttl_s"]


def test_weather_tile_validation_rejects_unknown_time_model():
    from api.routers.weather import _validate_time_model

    with pytest.raises(HTTPException):
        _validate_time_model("+99h", "best_match")
    with pytest.raises(HTTPException):
        _validate_time_model("now", "unknown_model")


def test_operation_suitability_flags_bad_spraying_conditions():
    from api.routers.weather import _operation_suitability

    decision = _operation_suitability(
        _sample(wind_speed_10m_kmh=31.0, wind_gusts_10m_kmh=43.0, precipitation_mm=1.2),
        "spraying",
    )
    assert decision["score"] < 0.35
    assert decision["suitability"] == "unsafe"
    assert "wind_speed_high" in decision["limiting_factors"]
    assert "precipitation_present" in decision["limiting_factors"]


@pytest.mark.asyncio
async def test_weather_tile_data_uses_cache_after_first_fetch(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()
    calls = {"n": 0}

    async def fake_fetch(lat, lon, time_key="now", model="best_match", **_kw):
        calls["n"] += 1
        return _sample(temperature_2m_c=33.0)

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_fetch)
    first = await weather.weather_tile_data(
        5, 16, 14, layer="temperature", time="now", model="best_match"
    )
    second = await weather.weather_tile_data(
        5, 16, 14, layer="temperature", time="now", model="best_match"
    )
    assert calls["n"] == 1
    assert first["value"] == 33.0
    assert second["cache_state"] == "fresh"


@pytest.mark.asyncio
async def test_weather_tile_data_returns_stale_cache_on_upstream_failure(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()
    key = "5:16:14:now:best_match"
    # اجعل العينة أقدم من TTL الطازج، وأصغر من stale TTL.
    weather._WEATHER_TILE_CACHE[key] = (
        weather.monotonic() - weather._WEATHER_TILE_CACHE_TTL_S - 5,
        _sample(temperature_2m_c=29.0),
    )

    async def failing_fetch(*_args, **_kwargs):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", failing_fetch)
    res = await weather.weather_tile_data(
        5, 16, 14, layer="temperature", time="now", model="best_match"
    )
    assert res["value"] == 29.0
    assert res["cache_state"] == "stale_fallback"
    assert "upstream down" in res["upstream_error"]
