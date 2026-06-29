"""V28 — Meteoblue-style soil temperature 10-40 cm down layer."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_manifest_advertises_soil_temperature_10_40cm_layer():
    from api.routers import weather

    manifest = weather.weather_layers_manifest()
    layers = {layer["key"]: layer for layer in manifest["layers"]}
    assert "soil_temperature_10_40cm" in layers
    assert layers["soil_temperature_10_40cm"]["depth"] == "10-40 cm down"
    assert layers["soil_temperature_10_40cm"]["derived"] is True


def test_soil_temperature_10_40cm_derived_value():
    from api.routers import weather

    sample = {
        "soil_temperature_6cm_c": 30.0,
        "soil_temperature_18cm_c": 25.0,
        "soil_temperature_54cm_c": 21.0,
    }
    value = weather._safe_layer_value("soil_temperature_10_40cm", sample)
    assert value is not None
    # 18 cm anchor + interpolated 40 cm value from 18/54 cm should sit between 21 and 25.
    assert 22.0 <= value <= 25.0


@pytest.mark.asyncio
async def test_weather_tile_data_supports_soil_temperature_10_40cm(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()

    async def fake_fetch(lat: float, lon: float, time_key: str = "now", model: str = "best_match"):
        return {
            "temperature_2m_c": 30.0,
            "wind_speed_10m_kmh": 8.0,
            "wind_direction_10m_deg": 270.0,
            "soil_temperature_6cm_c": 29.0,
            "soil_temperature_18cm_c": 25.0,
            "soil_temperature_54cm_c": 21.0,
            "soil_temperature_10_40cm_c": 23.9,
        }

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_fetch)
    result = await weather.weather_tile_data(
        5,
        16,
        14,
        layer="soil_temperature_10_40cm",
        time="now",
        model="best_match",
        interpolation="center",
    )

    assert result["layer"] == "soil_temperature_10_40cm"
    assert result["unit"] == "°C"
    assert result["value"] == 23.9
