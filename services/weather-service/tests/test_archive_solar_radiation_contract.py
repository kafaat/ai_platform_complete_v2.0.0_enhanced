"""Weather-service archive provides measured solar MJ/m2 to season consumers."""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import open_meteo  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_historical_fetch_requests_and_preserves_shortwave_radiation(monkeypatch):
    captured = {}

    async def fake_fetch(url, params):
        captured["url"] = url
        captured["daily"] = params["daily"].split(",")
        return {
            "daily": {
                "time": ["2026-01-01", "2026-01-02"],
                "temperature_2m_min": [12.0, 10.0],
                "temperature_2m_max": [28.0, 26.0],
                "precipitation_sum": [0.0, None],
                "et0_fao_evapotranspiration": [4.0, 4.1],
                "shortwave_radiation_sum": [18.5, 21.4],
            },
            "timezone": "Asia/Aden",
        }

    monkeypatch.setattr(open_meteo, "_fetch_json", fake_fetch)
    product = await open_meteo.fetch_historical(
        15.0, 44.0, start_date="2026-01-01", end_date="2026-01-02"
    )
    assert "shortwave_radiation_sum" in captured["daily"]
    assert product["days"][0]["solar_radiation_mj_m2"] == 18.5
    assert product["days"][1]["solar_radiation_mj_m2"] == 21.4
    assert product["days"][1]["precipitation_mm"] is None  # not measured zero
