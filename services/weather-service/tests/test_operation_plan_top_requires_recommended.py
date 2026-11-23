"""G1 — the operation plan offers no top recommendation when no window is recommended.

`operation_plan` computes a per-operation `recommended` flag, but `top_recommendation` used to
be the highest-ranked item whatever that flag said. A consumer that saves "the top
recommendation" (the platform's task/recommendation save paths) then saved a window the plan
itself did not recommend. These tests use the existing `recommended` flag only; they add no
threshold of their own.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

main = importlib.import_module("main")
cache = importlib.import_module("cache")

pytestmark = pytest.mark.unit


def _sample(**overrides):
    base = {
        "location": {"lat": 15.0, "lon": 44.0},
        "temperature_c": 24.0,
        "humidity_pct": 55.0,
        "wind_speed_10m_kmh": 9.0,
        "wind_gusts_10m_kmh": 12.0,
        "precipitation_mm": 0.0,
        "cloud_cover_pct": 20,
        "et0_mm": 4.2,
        "vpd_kpa": 1.4,
        "soil_temperature_6cm_c": 21.0,
        "soil_moisture_1_to_3cm_m3m3": 0.22,
        "surface_pressure_hpa": 890,
        "time": "2026-07-08T12:00",
        "source": "open-meteo",
    }
    base.update(overrides)
    return base


def _plan(monkeypatch, sample, operations):
    cache._CACHE.clear()

    async def tile(lat, lon, time_key="now", model="best_match"):
        return sample

    monkeypatch.setattr(main, "fetch_tile_sample", tile)
    client = TestClient(main.app)
    return client.get(
        f"/v1/weather/operation-plan?lat=15&lon=44&operations={operations}&hours=0,3"
    ).json()


def test_no_top_recommendation_when_no_window_is_recommended(monkeypatch):
    # Spraying with the wind input missing fails closed (insufficient_data, score 0), so the
    # plan's own flag says "not recommended" for every frame.
    sample = _sample()
    sample.pop("wind_speed_10m_kmh")
    sample.pop("wind_gusts_10m_kmh")
    plan = _plan(monkeypatch, sample, "spraying")
    assert plan["operations"], plan
    assert all(item["recommended"] is False for item in plan["operations"])
    assert plan["recommended_now"] == []
    assert plan["top_recommendation"] is None


def test_top_recommendation_is_a_recommended_item_when_one_exists(monkeypatch):
    plan = _plan(monkeypatch, _sample(), "spraying,harvesting")
    recommended = [item for item in plan["operations"] if item["recommended"]]
    assert recommended, plan
    assert plan["top_recommendation"] is not None
    assert plan["top_recommendation"]["recommended"] is True
    assert plan["top_recommendation"]["operation"] == recommended[0]["operation"]
