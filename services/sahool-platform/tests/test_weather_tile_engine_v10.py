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


# NOTE (P3.4): the tile runtime — fresh-cache reuse, stale-cache fallback on upstream
# failure, and the neutral-tile guarantee (value=null/200, never 502 per tile) — moved to
# weather-service, which now owns tile math, cache, and provider calls. The platform
# tile-data route is a thin facade. Those runtime behaviors are covered in weather-service:
#   - fresh reuse + stale fallback: test_p3_4_weather_service_runtime_coverage.py
#   - neutral tile on total upstream failure: test_p3_tile_neutral_resilience.py
# The neutral fallback across the platform->weather-service hop (facade returns a neutral
# tile on a 502) is covered by tests/test_p3_4_weather_facade_neutral.py. The pure manifest,
# validation, and operation-suitability contracts above remain platform-owned and stay here.
