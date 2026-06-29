"""V24 — Redis-ready weather cache tests.

These tests keep Redis optional: they use a small fake async client and verify that
SAHOOL can run with memory cache locally while being Redis-ready in production.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value
        self.ttl[key] = ttl
        return True


@pytest.mark.asyncio
async def test_weather_cache_defaults_to_memory_backend(monkeypatch):
    from api.routers import weather

    monkeypatch.delenv("SAHOOL_WEATHER_CACHE_BACKEND", raising=False)
    monkeypatch.delenv("WEATHER_CACHE_BACKEND", raising=False)
    monkeypatch.delenv("SAHOOL_WEATHER_REDIS_URL", raising=False)
    monkeypatch.delenv("WEATHER_REDIS_URL", raising=False)
    monkeypatch.setattr(weather, "_WEATHER_REDIS_CLIENT", None)
    weather._WEATHER_TILE_CACHE.clear()

    await weather._cache_set_async("unit:memory", {"temperature_2m_c": 25})
    sample, state, age = await weather._cache_get_async("unit:memory")

    assert sample == {"temperature_2m_c": 25}
    assert state == "fresh"
    assert isinstance(age, int)
    backend = weather.weather_tile_cache_backend()
    assert backend["backend"] == "memory"
    assert backend["effective_backend"] == "memory"


@pytest.mark.asyncio
async def test_weather_cache_can_use_redis_backend_with_fake_client(monkeypatch):
    from api.routers import weather

    fake = FakeRedis()
    monkeypatch.setenv("SAHOOL_WEATHER_CACHE_BACKEND", "redis")
    monkeypatch.setenv("SAHOOL_WEATHER_REDIS_URL", "redis://unit-test:6379/0")
    monkeypatch.setattr(weather, "_WEATHER_REDIS_CLIENT", fake)
    weather._WEATHER_TILE_CACHE.clear()

    await weather._cache_set_async("unit:redis", {"wind_speed_10m_kmh": 12})
    sample, state, age = await weather._cache_get_async("unit:redis")

    assert sample == {"wind_speed_10m_kmh": 12}
    assert state == "fresh"
    assert isinstance(age, int)
    assert fake.ttl[weather._redis_cache_key("unit:redis")] == int(
        weather._WEATHER_TILE_STALE_TTL_S
    )
    backend = weather.weather_tile_cache_backend()
    assert backend["backend"] == "redis"
    assert backend["effective_backend"] == "redis+memory-fallback"


@pytest.mark.asyncio
async def test_weather_cache_redis_missing_url_falls_back_to_memory(monkeypatch):
    from api.routers import weather

    monkeypatch.setenv("SAHOOL_WEATHER_CACHE_BACKEND", "redis")
    monkeypatch.delenv("SAHOOL_WEATHER_REDIS_URL", raising=False)
    monkeypatch.delenv("WEATHER_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("SAHOOL_WEATHER_REDIS_FALLBACK_MEMORY", "1")
    monkeypatch.setattr(weather, "_WEATHER_REDIS_CLIENT", None)
    weather._WEATHER_TILE_CACHE.clear()

    await weather._cache_set_async("unit:fallback", {"cloud_cover_pct": 20})
    sample, state, _age = await weather._cache_get_async("unit:fallback")

    assert sample == {"cloud_cover_pct": 20}
    assert state == "fresh"
    backend = weather.weather_tile_cache_backend()
    assert backend["backend"] == "redis"
    assert backend["redis_configured"] is False
    assert backend["fallback_to_memory"] is True


def test_weather_manifest_advertises_cache_backend_endpoint(monkeypatch):
    from api.routers import weather

    manifest = weather.weather_layers_manifest()
    assert "/api/v1/weather/tile-cache/backend" in manifest["observability_endpoints"]
    assert "backend" in manifest["cache"]
    prom = weather._weather_metrics_prometheus()
    assert "sahool_weather_cache_backend_total" in prom
