from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))


@pytest.mark.skipif(not os.getenv("WEATHER_REDIS_INTEGRATION_URL"), reason="set WEATHER_REDIS_INTEGRATION_URL to run live Redis cache integration")
def test_weather_cache_live_redis_roundtrip(monkeypatch):
    cache = importlib.import_module("cache")
    monkeypatch.setattr(cache, "REDIS_URL", os.environ["WEATHER_REDIS_INTEGRATION_URL"])
    monkeypatch.setattr(cache, "_REDIS_CLIENT", None)
    monkeypatch.setattr(cache, "_REDIS_ERROR", None)

    key = "live-redis-roundtrip"
    payload = {"source": "integration", "temperature_c": 31.2}
    cache.set(key, payload)
    value, state, age = cache.get(key)
    stats = cache.stats()

    assert value == payload
    assert state == "fresh"
    assert age == 0
    assert stats["backend"] == "redis"
