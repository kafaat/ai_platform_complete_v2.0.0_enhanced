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


# NOTE (P3.4): the tile-data endpoint's derived soil_temperature_10_40cm rendering moved to
# weather-service (the platform route is now a thin facade). The endpoint-integration test
# now lives in services/weather-service/tests/ (test_p3_tile_neutral_resilience.py::
# test_tile_data_supports_soil_temperature_depth_layer). The manifest advertisement and the
# pure derivation contract above remain platform-owned and stay here.
