"""Derived agronomic operational-risk weather layers.

Covers the three DERIVED (non provider-native) layers added on top of the
existing Open-Meteo sample fields:
  - spraying_drift_risk  (0..1, higher = riskier to spray)
  - soil_trafficability  (0..1, higher = safer to drive machinery)
  - heat_stress          (0..1, higher = more crop/livestock heat stress)
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

_DERIVED_RISK_LAYERS = ("spraying_drift_risk", "soil_trafficability", "heat_stress")


def test_manifest_advertises_agronomic_risk_layers():
    from api.routers import weather

    manifest = weather.weather_layers_manifest()
    layers = {layer["key"]: layer for layer in manifest["layers"]}
    for key in _DERIVED_RISK_LAYERS:
        assert key in layers, f"{key} missing from manifest"
        assert layers[key]["derived"] is True
        assert layers[key]["provider_native"] is False
        assert layers[key]["unit"] == "0..1"
    assert layers["spraying_drift_risk"]["kind"] == "risk"
    assert layers["soil_trafficability"]["kind"] == "operation"
    assert layers["heat_stress"]["kind"] == "risk"


def test_risk_layers_are_allowed_tile_layers():
    from api.routers import weather

    for key in _DERIVED_RISK_LAYERS:
        assert key in weather._ALLOWED_WEATHER_TILE_LAYERS


# --- spraying drift risk -------------------------------------------------


def test_spraying_drift_risk_safe_conditions():
    from api.routers import weather

    safe = {
        "wind_speed_10m_kmh": 5.0,
        "wind_gusts_10m_kmh": 12.0,
        "vapour_pressure_deficit_kpa": 1.0,
        "precipitation_mm": 0.0,
    }
    value = weather._safe_layer_value("spraying_drift_risk", safe)
    assert value is not None
    assert value < 0.2


def test_spraying_drift_risk_high_wind():
    from api.routers import weather

    risky = {
        "wind_speed_10m_kmh": 26.0,
        "wind_gusts_10m_kmh": 40.0,
        "vapour_pressure_deficit_kpa": 4.0,
        "precipitation_mm": 0.0,
    }
    value = weather._safe_layer_value("spraying_drift_risk", risky)
    assert value is not None
    assert value > 0.85


def test_spraying_drift_risk_active_rain_forces_max():
    from api.routers import weather

    sample = {"wind_speed_10m_kmh": 2.0, "precipitation_mm": 0.5}
    assert weather._safe_layer_value("spraying_drift_risk", sample) == 1.0


def test_spraying_drift_risk_missing_fields_returns_none():
    from api.routers import weather

    assert weather._safe_layer_value("spraying_drift_risk", {}) is None
    # precipitation alone is not a driver field -> still None
    assert weather._safe_layer_value("spraying_drift_risk", {"precipitation_mm": 0.0}) is None


# --- soil trafficability -------------------------------------------------


def test_soil_trafficability_dry_soil_is_safe():
    from api.routers import weather

    value = weather._safe_layer_value("soil_trafficability", {"soil_moisture_1_to_3cm_m3m3": 0.18})
    assert value == 1.0


def test_soil_trafficability_saturated_soil_is_unsafe():
    from api.routers import weather

    value = weather._safe_layer_value("soil_trafficability", {"soil_moisture_1_to_3cm_m3m3": 0.45})
    assert value == 0.0


def test_soil_trafficability_recent_rain_caps_score():
    from api.routers import weather

    # Dry reading but heavy recent rain keeps the surface slick -> capped at 0.5.
    value = weather._safe_layer_value(
        "soil_trafficability",
        {"soil_moisture_1_to_3cm_m3m3": 0.18, "precipitation_mm": 8.0},
    )
    assert value == 0.5


def test_soil_trafficability_falls_back_to_surface_layer():
    from api.routers import weather

    value = weather._safe_layer_value("soil_trafficability", {"soil_moisture_0_to_1cm_m3m3": 0.30})
    assert value is not None
    assert 0.0 < value < 1.0


def test_soil_trafficability_missing_fields_returns_none():
    from api.routers import weather

    assert weather._safe_layer_value("soil_trafficability", {}) is None


# --- heat stress ---------------------------------------------------------


def test_heat_stress_mild_temperature_is_safe():
    from api.routers import weather

    value = weather._safe_layer_value(
        "heat_stress", {"temperature_2m_c": 24.0, "relative_humidity_2m_pct": 40.0}
    )
    assert value == 0.0


def test_heat_stress_extreme_heat_is_severe():
    from api.routers import weather

    value = weather._safe_layer_value(
        "heat_stress", {"temperature_2m_c": 43.0, "relative_humidity_2m_pct": 50.0}
    )
    assert value == 1.0


def test_heat_stress_humidity_raises_index():
    from api.routers import weather

    dry = weather._safe_layer_value(
        "heat_stress", {"temperature_2m_c": 35.0, "relative_humidity_2m_pct": 30.0}
    )
    humid = weather._safe_layer_value(
        "heat_stress", {"temperature_2m_c": 35.0, "relative_humidity_2m_pct": 90.0}
    )
    assert dry is not None and humid is not None
    assert humid > dry


def test_heat_stress_missing_temperature_returns_none():
    from api.routers import weather

    assert weather._safe_layer_value("heat_stress", {}) is None
    assert weather._safe_layer_value("heat_stress", {"relative_humidity_2m_pct": 80.0}) is None


# NOTE (P3.4): the tile-data endpoint's derived-layer rendering (heat_stress via
# GET /tile-data) moved to weather-service; the platform route is now a thin facade.
# The equivalent endpoint-integration test lives in
# services/weather-service/tests/test_p3_4_weather_service_runtime_coverage.py. The pure
# _safe_layer_value derivation above remains a platform unit contract and stays here.
