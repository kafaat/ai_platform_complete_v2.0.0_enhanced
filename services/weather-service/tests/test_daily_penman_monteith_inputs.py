"""مدخلا Penman-Monteith اليوميّان: الرطوبة **المتوسّطة** والريح **المتوسّطة على 10م**.

دفتر الماء اليوميّ كان يطلب ET0 بلا رطوبة، فيسقط المحرّك إلى Hargreaves المتدهور دائماً.
والريح المتاحة كانت ``wind_speed_10m_max`` — قصوى اليوم على 10م — لا تصلح ``u2``. فيُطلَب
من Open-Meteo ``relative_humidity_2m_mean`` و``wind_speed_10m_mean`` (متغيّران يوميّان
موثَّقان في مصدر موقعه الرسميّ)، ويُطبَّعان بأسماءٍ تحمل الارتفاع، وغيابُهما ``None`` لا صفر.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import open_meteo  # noqa: E402
from canonical_weather_state import _DAILY_OPTIONAL_DAY_FIELDS  # noqa: E402

pytestmark = pytest.mark.unit


def test_the_forecast_requests_daily_mean_humidity_and_mean_wind(monkeypatch):
    captured: dict = {}

    async def _fake_fetch(url, params):
        captured.update(params)
        return {"daily": {"time": []}}

    monkeypatch.setattr(open_meteo, "_fetch_json", _fake_fetch)
    asyncio.run(open_meteo.fetch_forecast(15.3, 44.2, days=1))
    requested = captured["daily"].split(",")
    assert "relative_humidity_2m_mean" in requested
    assert "wind_speed_10m_mean" in requested


def test_daily_means_are_normalised_with_height_in_the_name():
    data = {
        "daily": {
            "time": ["2026-06-01"],
            "wind_speed_10m_mean": [14.4],  # km/h ⇒ 4.0 m/s
            "wind_speed_10m_max": [36.0],
            "relative_humidity_2m_mean": [38],
        }
    }
    day = open_meteo.normalize_daily(data, lat=0, lon=0, source="t", model="m")["days"][0]
    assert day["wind_mean_10m_ms"] == pytest.approx(4.0)
    assert day["rh_mean_pct"] == 38
    assert day["wind_max_ms"] == pytest.approx(10.0), "القصوى باقية لمستهلكيها، منفصلة"


def test_absent_means_stay_absent_not_zero():
    data = {"daily": {"time": ["2026-06-01"]}}
    day = open_meteo.normalize_daily(data, lat=0, lon=0, source="t", model="m")["days"][0]
    assert day["wind_mean_10m_ms"] is None and day["rh_mean_pct"] is None


def test_the_envelope_counts_them_as_optional_forecast_fields():
    assert {"rh_mean_pct", "wind_mean_10m_ms"} <= set(_DAILY_OPTIONAL_DAY_FIELDS)
