from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))


@pytest.mark.skipif(
    not os.getenv("WEATHER_REDIS_INTEGRATION_URL"),
    reason="set WEATHER_REDIS_INTEGRATION_URL to run live Redis cache integration",
)
def test_weather_cache_live_redis_roundtrip(monkeypatch):
    cache = importlib.import_module("cache")
    monkeypatch.setattr(cache, "REDIS_URL", os.environ["WEATHER_REDIS_INTEGRATION_URL"])
    monkeypatch.setattr(cache, "_REDIS_CLIENT", None)
    monkeypatch.setattr(cache, "_REDIS_ERROR", None)

    import redis

    key = "live-redis-roundtrip-" + uuid4().hex
    payload = {"source": "integration", "temperature_c": 31.2}
    keys = [cache._fresh_key(key), cache._stale_key(key)]
    with redis.Redis.from_url(cache.REDIS_URL) as observer:
        try:
            cache.set(key, payload)
            assert [json.loads(raw) for raw in observer.mget(keys)] == [{"value": payload}] * 2
            for redis_key, ttl in zip(keys, (cache.TTL_S, cache.STALE_TTL_S), strict=True):
                assert 0 < observer.ttl(redis_key) <= int(ttl)
            assert key not in cache._CACHE
            value, state, age = cache.get(key)
            assert value == payload
            assert state == "fresh"
            assert isinstance(age, int) and 0 <= age <= int(cache.TTL_S)
            stats = cache.stats()
            assert stats["backend"] == "redis"
            assert "redis_error" not in stats
        finally:
            observer.delete(*keys)
