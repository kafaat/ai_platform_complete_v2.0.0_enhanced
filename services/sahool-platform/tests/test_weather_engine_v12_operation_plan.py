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


# NOTE (P3.4): operation-plan ranking and partial-on-frame-failure are runtime behaviors that
# moved to weather-service (the platform route is now a thin facade to it). The equivalent
# runtime tests now live in
# services/weather-service/tests/test_p3_4_weather_service_runtime_coverage.py. The pure
# _parse_operations_csv validation contract above remains platform-owned and stays here.
