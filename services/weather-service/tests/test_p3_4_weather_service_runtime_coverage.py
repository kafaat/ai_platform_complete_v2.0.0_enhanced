"""P3.4 — weather-service runtime coverage for behaviors that moved out of sahool-platform.

When the platform weather routes became thin facades (P3.4), the tests that used to assert
these behaviors against the in-platform provider path were removed from sahool-platform. The
behaviors themselves now live in weather-service, so their coverage moves here:

  - fresh-cache reuse (second read served from cache, provider called once)
  - stale-cache fallback on upstream failure
  - operation-window best-future-frame selection
  - operation-window partial handling when one frame fails
  - operation-plan ranking (irrigation need floats to the top)
  - derived risk-layer rendering via the tile endpoint (heat_stress)

weather-service is a standalone FastAPI app; we drive it with TestClient(main.app) and
monkeypatch the provider seam (main.fetch_tile_sample), mirroring
test_p3_weather_service_runtime.py / test_p3_tile_neutral_resilience.py.
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


def test_tile_data_reuses_fresh_cache_after_first_fetch(monkeypatch):
    """Second identical read is served from fresh cache; provider is called once."""
    cache._CACHE.clear()
    calls = {"n": 0}

    async def counting_tile(lat, lon, time_key="now", model="best_match"):
        calls["n"] += 1
        return _sample(temperature_c=33.0)

    monkeypatch.setattr(main, "fetch_tile_sample", counting_tile)
    client = TestClient(main.app)
    first = client.get("/v1/weather/tile-data/5/16/14?layer=temperature").json()
    second = client.get("/v1/weather/tile-data/5/16/14?layer=temperature").json()
    assert calls["n"] == 1
    assert first["value"] == 33.0
    assert first["cache_state"] == "refreshed"
    assert second["cache_state"] == "fresh"


def test_tile_data_returns_stale_cache_on_upstream_failure(monkeypatch):
    """A warm (then-failing) cache serves stale data instead of erroring."""
    cache._CACHE.clear()

    async def ok_tile(lat, lon, time_key="now", model="best_match"):
        return _sample(temperature_c=29.0)

    monkeypatch.setattr(main, "fetch_tile_sample", ok_tile)
    client = TestClient(main.app)
    client.get("/v1/weather/tile-data/5/16/14?layer=temperature")  # warm the cache

    # Age the single cache entry past fresh TTL but within stale TTL so the next read,
    # with the provider now down, must serve the stale value instead of erroring.
    aged_ts = cache.monotonic() - cache.TTL_S - 5.0
    for key, (_ts, sample) in list(cache._CACHE.items()):
        cache._CACHE[key] = (aged_ts, sample)

    async def failing_tile(*_a, **_k):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(main, "fetch_tile_sample", failing_tile)
    res = client.get("/v1/weather/tile-data/5/16/14?layer=temperature").json()
    assert res["value"] == 29.0
    assert res["cache_state"] == "stale_fallback"
    assert "upstream down" in (res["upstream_error"] or "")


def test_operation_window_selects_best_future_frame(monkeypatch):
    """The 'now' frame is unsafe (high wind + rain); a calm future frame wins."""
    cache._CACHE.clear()

    async def frame_tile(lat, lon, time_key="now", model="best_match"):
        if time_key == "now":
            return _sample(wind_speed_10m_kmh=40.0, wind_gusts_10m_kmh=52.0, precipitation_mm=1.0)
        if time_key == "+3h":
            return _sample(wind_speed_10m_kmh=8.0, wind_gusts_10m_kmh=12.0, precipitation_mm=0.0)
        return _sample(wind_speed_10m_kmh=17.0, wind_gusts_10m_kmh=22.0, precipitation_mm=0.0)

    monkeypatch.setattr(main, "fetch_tile_sample", frame_tile)
    client = TestClient(main.app)
    res = client.get(
        "/v1/weather/operation-window?lat=15&lon=44&operation=spraying&hours=0,3,6"
    ).json()
    assert res["best"]["time"] == "+3h"
    assert res["best"]["operation"]["suitability"] in {"optimal", "acceptable"}
    assert res["frames"][0]["operation"]["suitability"] == "unsafe"
    assert res["partial"] is False


def test_operation_window_is_partial_when_one_frame_fails(monkeypatch):
    """A single failing frame degrades to partial (not a hard error)."""
    cache._CACHE.clear()

    async def flaky_tile(lat, lon, time_key="now", model="best_match"):
        if time_key == "+1h":
            raise RuntimeError("frame +1h failed")
        return _sample()

    monkeypatch.setattr(main, "fetch_tile_sample", flaky_tile)
    client = TestClient(main.app)
    res = client.get(
        "/v1/weather/operation-window?lat=15&lon=44&operation=spraying&hours=0,1,3"
    ).json()
    assert len(res["frames"]) == 2
    assert res["partial"] is True
    assert any("+1h" in e for e in res["upstream_errors"])


def test_operation_plan_ranks_irrigation_need(monkeypatch):
    """Low soil moisture + no rain floats irrigation above a wind-limited spraying op."""
    cache._CACHE.clear()

    async def dry_tile(lat, lon, time_key="now", model="best_match"):
        # Dry soil (irrigation-favourable), but too windy to spray.
        return _sample(
            wind_speed_10m_kmh=40.0,
            wind_gusts_10m_kmh=52.0,
            precipitation_mm=0.0,
            soil_moisture_1_to_3cm_m3m3=0.14,
        )

    monkeypatch.setattr(main, "fetch_tile_sample", dry_tile)
    client = TestClient(main.app)
    plan = client.get(
        "/v1/weather/operation-plan?lat=15&lon=44&operations=spraying,irrigation&hours=0,3"
    ).json()
    assert plan["operations"][0]["operation"] == "irrigation"
    assert plan["operations"][0]["recommended"] is True
    assert plan["top_recommendation"]["operation"] == "irrigation"


def test_tile_data_supports_derived_heat_stress_layer(monkeypatch):
    """A derived risk layer (heat_stress) renders via the tile endpoint post-extraction."""
    cache._CACHE.clear()

    async def hot_tile(lat, lon, time_key="now", model="best_match"):
        return _sample(temperature_c=43.0)

    monkeypatch.setattr(main, "fetch_tile_sample", hot_tile)
    client = TestClient(main.app)
    body = client.get("/v1/weather/tile-data/5/16/14?layer=heat_stress").json()
    assert body["layer"] == "heat_stress"
    assert body["unit"] == "0..1"
    assert body["value"] == 1.0
