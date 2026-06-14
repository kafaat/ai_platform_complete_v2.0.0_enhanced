"""حقول الطقس الشمسيّة/النهاريّة (شروق/غروب/مدّة النهار/الإشعاع) — لجدولة الريّ
بالطاقة الشمسيّة. يثبّت تحليل الموصِّل (_build_daily) + كشف الحقول في نقطة التوقّع.
"""

from __future__ import annotations

import os
import re
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
MAIN = os.path.join(CORE, "api", "main.py")


@pytest.fixture(scope="module")
def om():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("httpx")
    from api.connectors import openmeteo

    return openmeteo


def test_build_daily_extracts_solar_and_daylight(om):
    d = {
        "temperature_2m_max": [31.0],
        "temperature_2m_min": [17.0],
        "precipitation_sum": [0.0],
        "et0_fao_evapotranspiration": [4.2],
        "sunshine_duration": [36000],  # 10h
        "wind_speed_10m_max": [3.0],
        "weather_code": [0],
        "sunrise": ["2026-06-14T05:40"],
        "sunset": ["2026-06-14T18:30"],
        "daylight_duration": [46800],  # 13h
        "shortwave_radiation_sum": [28.5],  # MJ/m²
    }
    f = om._build_daily(d, 0, "2026-06-14")
    assert f.sunrise == "2026-06-14T05:40"
    assert f.sunset == "2026-06-14T18:30"
    assert f.daylight_hours == 13.0  # 46800s → ساعات
    assert f.solar_radiation_mj_m2 == 28.5
    assert f.sunshine_hours == 10.0


def test_build_daily_missing_solar_is_none(om):
    """fail-safe: غياب الحقول (مصدر قديم/قيمة null) ⇒ None لا انهيار."""
    f = om._build_daily({}, 0, "2026-06-14")
    assert f.sunrise is None
    assert f.sunset is None
    assert f.daylight_hours is None
    assert f.solar_radiation_mj_m2 is None


def test_daily_keys_request_solar(om):
    """طلب Open-Meteo اليوميّ يتضمّن مفاتيح الشمس/النهار."""
    keys = set(om._DAILY_KEYS)
    assert {"sunrise", "sunset", "daylight_duration", "shortwave_radiation_sum"} <= keys


def test_forecast_endpoint_exposes_solar_fields():
    """نقطة /api/v1/weather/forecast تكشف الحقول الجديدة في كلّ يوم."""
    with open(MAIN, encoding="utf-8") as f:
        src = f.read()
    start = src.index("async def weather_forecast(")
    nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
    body = src[start : start + 1 + nxt.start()]
    for key in ('"sunrise"', '"sunset"', '"daylight_hours"', '"solar_radiation_mj_m2"'):
        assert key in body, f"نقطة التوقّع لا تكشف {key}"
