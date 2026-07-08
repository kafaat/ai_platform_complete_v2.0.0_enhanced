"""P3.5 — weather-service tile resilience (moved from sahool-platform in the P3 extraction).

Locks the behaviors the platform tile runtime used to own, now that weather-service owns
them: the neutral-tile guarantee on total upstream failure (no 500/no per-tile flood) and
soil-temperature depth layers. The neutral case is a regression the P3 extraction had
dropped (_cached_sample re-raised with no cache); it is fixed and locked here.
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
        "soil_temperature_6cm_c": 20.0,
        "soil_temperature_18cm_c": 19.0,
        "soil_temperature_54cm_c": 18.0,
        "time": "2026-07-08T12:00",
        "source": "open-meteo",
    }
    base.update(overrides)
    return base


def test_tile_data_returns_neutral_tile_when_upstream_down_and_no_cache(monkeypatch):
    """Open-Meteo down + no cache ⇒ neutral tile (value=null, 200), never 500/flood."""
    cache._CACHE.clear()

    async def failing_tile(*_a, **_k):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(main, "fetch_tile_sample", failing_tile)
    client = TestClient(main.app)
    resp = client.get("/v1/weather/tile-data/5/16/14?layer=temperature")
    assert resp.status_code == 200  # not 500, not 502
    body = resp.json()
    assert body["value"] is None
    assert body["sample"] is None
    assert body["cache_state"] == "unavailable"
    assert "upstream" in (body["upstream_error"] or "").lower()


def test_tile_data_supports_soil_temperature_depth_layer(monkeypatch):
    cache._CACHE.clear()

    async def ok_tile(lat, lon, time_key="now", model="best_match"):
        return _sample(location={"lat": lat, "lon": lon})

    monkeypatch.setattr(main, "fetch_tile_sample", ok_tile)
    client = TestClient(main.app)
    body = client.get("/v1/weather/tile-data/5/16/14?layer=soil_temperature_10_40cm").json()
    assert body["layer"] == "soil_temperature_10_40cm"
    assert body["value"] is not None
    assert body["unit"] == "°C"
