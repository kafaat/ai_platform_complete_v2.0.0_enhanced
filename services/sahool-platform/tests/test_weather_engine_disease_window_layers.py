"""Derived disease-window risk weather layers.

Covers the three DERIVED (non provider-native) crop-disease infection-window
proxy layers added on top of the existing Open-Meteo sample fields:
  - disease_late_blight   (0..1, potato — Phytophthora infestans)
  - disease_downy_mildew  (0..1, grape — Plasmopara viticola)
  - disease_stripe_rust   (0..1, wheat — Puccinia striiformis)

Each is a single-timestep favourability proxy, NOT a full multi-day infection
model; the tests assert the high-risk vs low-risk separation and the
None-on-missing-input contract, mirroring the agronomic-risk layer tests.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

_DISEASE_LAYERS = ("disease_late_blight", "disease_downy_mildew", "disease_stripe_rust")


def test_manifest_advertises_disease_window_layers():
    from api.routers import weather

    manifest = weather.weather_layers_manifest()
    layers = {layer["key"]: layer for layer in manifest["layers"]}
    for key in _DISEASE_LAYERS:
        assert key in layers, f"{key} missing from manifest"
        assert layers[key]["derived"] is True
        assert layers[key]["provider_native"] is False
        assert layers[key]["unit"] == "0..1"
        assert layers[key]["kind"] == "risk"
    assert layers["disease_late_blight"]["pathogen"] == "Phytophthora infestans"
    assert layers["disease_downy_mildew"]["pathogen"] == "Plasmopara viticola"
    assert layers["disease_stripe_rust"]["pathogen"] == "Puccinia striiformis"


def test_disease_layers_are_allowed_tile_layers():
    from api.routers import weather

    for key in _DISEASE_LAYERS:
        assert key in weather._ALLOWED_WEATHER_TILE_LAYERS


def test_disease_layers_have_presets():
    from api.routers import weather

    manifest = weather.weather_layers_manifest()
    preset_layers = {preset["layer"] for preset in manifest["presets"]}
    for key in _DISEASE_LAYERS:
        assert key in preset_layers


# --- potato late blight (Phytophthora infestans) -------------------------


def test_late_blight_high_when_cool_humid_and_wet():
    from api.routers import weather

    value = weather._safe_layer_value(
        "disease_late_blight",
        {
            "temperature_2m_c": 18.0,
            "relative_humidity_2m_pct": 95.0,
            "precipitation_mm": 1.0,
        },
    )
    assert value is not None
    assert value > 0.6


def test_late_blight_low_when_hot_and_dry():
    from api.routers import weather

    value = weather._safe_layer_value(
        "disease_late_blight",
        {
            "temperature_2m_c": 33.0,
            "relative_humidity_2m_pct": 30.0,
            "precipitation_mm": 0.0,
        },
    )
    assert value is not None
    assert value < 0.1


def test_late_blight_dry_air_suppresses_index_even_when_cool():
    from api.routers import weather

    humid = weather._safe_layer_value(
        "disease_late_blight",
        {"temperature_2m_c": 18.0, "relative_humidity_2m_pct": 95.0},
    )
    dry = weather._safe_layer_value(
        "disease_late_blight",
        {"temperature_2m_c": 18.0, "relative_humidity_2m_pct": 70.0},
    )
    assert humid is not None and dry is not None
    assert humid > dry


def test_late_blight_missing_fields_returns_none():
    from api.routers import weather

    assert weather._safe_layer_value("disease_late_blight", {}) is None
    # temperature alone (no humidity/vpd) -> None
    assert weather._safe_layer_value("disease_late_blight", {"temperature_2m_c": 18.0}) is None
    # humidity without temperature -> None
    assert (
        weather._safe_layer_value("disease_late_blight", {"relative_humidity_2m_pct": 95.0}) is None
    )


# --- grape downy mildew (Plasmopara viticola) ----------------------------


def test_downy_mildew_high_when_warm_humid_and_rainy():
    from api.routers import weather

    value = weather._safe_layer_value(
        "disease_downy_mildew",
        {
            "temperature_2m_c": 22.0,
            "relative_humidity_2m_pct": 95.0,
            "precipitation_mm": 12.0,
        },
    )
    assert value is not None
    assert value > 0.8


def test_downy_mildew_low_when_cold_and_dry():
    from api.routers import weather

    value = weather._safe_layer_value(
        "disease_downy_mildew",
        {
            "temperature_2m_c": 5.0,
            "relative_humidity_2m_pct": 35.0,
            "precipitation_mm": 0.0,
        },
    )
    assert value is not None
    assert value < 0.1


def test_downy_mildew_rain_dominates_over_humidity():
    from api.routers import weather

    rainy = weather._safe_layer_value(
        "disease_downy_mildew",
        {"temperature_2m_c": 22.0, "precipitation_mm": 12.0},
    )
    humid_only = weather._safe_layer_value(
        "disease_downy_mildew",
        {"temperature_2m_c": 22.0, "relative_humidity_2m_pct": 95.0},
    )
    assert rainy is not None and humid_only is not None
    assert rainy > humid_only


def test_downy_mildew_missing_fields_returns_none():
    from api.routers import weather

    assert weather._safe_layer_value("disease_downy_mildew", {}) is None
    assert weather._safe_layer_value("disease_downy_mildew", {"temperature_2m_c": 22.0}) is None


# --- wheat stripe rust (Puccinia striiformis) ----------------------------


def test_stripe_rust_high_when_cool_and_wet():
    from api.routers import weather

    value = weather._safe_layer_value(
        "disease_stripe_rust",
        {"temperature_2m_c": 10.0, "relative_humidity_2m_pct": 96.0},
    )
    assert value is not None
    assert value > 0.8


def test_stripe_rust_suppressed_above_22c():
    from api.routers import weather

    value = weather._safe_layer_value(
        "disease_stripe_rust",
        {"temperature_2m_c": 28.0, "relative_humidity_2m_pct": 96.0},
    )
    assert value is not None
    assert value < 0.05


def test_stripe_rust_low_vpd_substitutes_for_humidity():
    from api.routers import weather

    value = weather._safe_layer_value(
        "disease_stripe_rust",
        {"temperature_2m_c": 10.0, "vapour_pressure_deficit_kpa": 0.1},
    )
    assert value is not None
    assert value > 0.8


def test_stripe_rust_missing_fields_returns_none():
    from api.routers import weather

    assert weather._safe_layer_value("disease_stripe_rust", {}) is None
    assert weather._safe_layer_value("disease_stripe_rust", {"temperature_2m_c": 10.0}) is None


# NOTE (P3.4): the tile-data endpoint's derived-layer rendering (disease windows via
# GET /tile-data) moved to weather-service; the platform route is now a thin facade to
# weather-service (which owns tile math + provider calls). The disease derivation formulas
# above stay here as pure platform unit contracts (_safe_layer_value). The endpoint no
# longer derives layers in-platform, so the former endpoint-integration test was removed.
