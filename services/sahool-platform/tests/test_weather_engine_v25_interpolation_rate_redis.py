"""V25 — spatial tile interpolation + Redis-backed multi-tenant rate limits."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class FakeRateRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self.expiries: dict[str, int] = {}

    async def incr(self, key: str):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, ttl: int):
        self.expiries[key] = ttl
        return True

    async def ttl(self, key: str):
        return self.expiries.get(key, 60)

    async def get(self, key: str):
        return None

    async def setex(self, key: str, ttl: int, value: str):
        return True


# NOTE (P3.4): spatial 2x2+center tile interpolation (tile-data and operation-tile-data grid
# mode) moved to weather-service; the platform routes are now thin facades. The grid
# interpolation runtime is covered in weather-service by
# services/weather-service/tests/test_p3_weather_service_runtime.py
# (test_p3_3_tile_data_operation_tile_series_and_wind_grid). The Redis-backed multi-tenant
# rate limiter below is a PLATFORM (BFF) concern and stays here.


@pytest.mark.asyncio
async def test_redis_rate_limit_backend_sets_headers_and_limits(monkeypatch):
    from api.routers import weather
    from fastapi import HTTPException
    from starlette.datastructures import Headers, QueryParams
    from starlette.responses import Response

    fake = FakeRateRedis()
    monkeypatch.setenv("SAHOOL_WEATHER_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setenv("SAHOOL_WEATHER_RATE_LIMIT_REDIS_URL", "redis://unit-test:6379/0")
    monkeypatch.setenv("SAHOOL_WEATHER_RATE_LIMIT_REDIS_FALLBACK_MEMORY", "0")
    monkeypatch.setattr(weather, "_WEATHER_REDIS_CLIENT", fake)
    old_limits = dict(weather._WEATHER_RATE_LIMITS)
    weather._WEATHER_RATE_LIMITS["unit-redis"] = (2, 60)

    class Req:
        headers = Headers({"x-tenant-id": "tenant-a", "x-user-id": "user-a"})
        query_params = QueryParams("")
        client = type("Client", (), {"host": "127.0.0.1"})()

    try:
        r1 = Response()
        await weather._enforce_weather_rate_limit_async(Req(), "unit-redis", r1)
        assert r1.headers["X-RateLimit-Backend"] == "redis"
        assert r1.headers["X-RateLimit-Remaining"] == "1"

        r2 = Response()
        await weather._enforce_weather_rate_limit_async(Req(), "unit-redis", r2)
        assert r2.headers["X-RateLimit-Remaining"] == "0"

        with pytest.raises(HTTPException) as exc:
            await weather._enforce_weather_rate_limit_async(Req(), "unit-redis", Response())
        assert exc.value.status_code == 429
        assert exc.value.headers["X-RateLimit-Backend"] == "redis"
    finally:
        weather._WEATHER_RATE_LIMITS.clear()
        weather._WEATHER_RATE_LIMITS.update(old_limits)
        monkeypatch.delenv("SAHOOL_WEATHER_RATE_LIMIT_BACKEND", raising=False)
        monkeypatch.delenv("SAHOOL_WEATHER_RATE_LIMIT_REDIS_URL", raising=False)
        monkeypatch.delenv("SAHOOL_WEATHER_RATE_LIMIT_REDIS_FALLBACK_MEMORY", raising=False)


def test_manifest_advertises_interpolation_and_rate_backend():
    from api.routers import weather

    manifest = weather.weather_layers_manifest()
    assert manifest["tile_interpolation"]["supported"] is True
    assert "grid" in manifest["tile_interpolation"]["modes"]
    assert "backend" in manifest["rate_limits"]
    assert "/api/v1/weather/rate-limit/backend" in manifest["observability_endpoints"]
    assert "sahool_weather_rate_limit_backend_total" in weather._weather_metrics_prometheus()
