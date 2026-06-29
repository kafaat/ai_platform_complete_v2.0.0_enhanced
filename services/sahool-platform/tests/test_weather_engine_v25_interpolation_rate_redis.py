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


@pytest.mark.asyncio
async def test_weather_tile_data_grid_interpolation(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()
    monkeypatch.delenv("SAHOOL_WEATHER_CACHE_BACKEND", raising=False)

    async def fake_fetch(lat: float, lon: float, time_key: str = "now", model: str = "best_match"):
        return {
            "temperature_2m_c": round(20 + lat * 0.01 + lon * 0.01, 3),
            "wind_speed_10m_kmh": 10,
            "wind_direction_10m_deg": 270,
            "relative_humidity_2m_pct": 50,
            "wind_gusts_10m_kmh": 14,
            "precipitation_mm": 0,
            "vapour_pressure_deficit_kpa": 1.2,
            "soil_moisture_1_to_3cm_m3m3": 0.23,
            "soil_temperature_6cm_c": 21,
        }

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_fetch)
    result = await weather.weather_tile_data(
        5, 16, 14, layer="temperature", time="now", model="best_match", interpolation="grid"
    )

    assert result["interpolation"]["mode"] == "bilinear_2x2_center"
    assert result["interpolation"]["point_count"] == 5
    assert {p["id"] for p in result["interpolation"]["points"]} == {
        "nw",
        "ne",
        "sw",
        "se",
        "center",
    }
    assert result["interpolation"]["average_value"] is not None
    assert result["cache_state"] in {"refreshed", "fresh", "partial"}


@pytest.mark.asyncio
async def test_weather_operation_tile_data_grid_interpolation(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    weather._WEATHER_TILE_CACHE.clear()

    async def fake_fetch(lat: float, lon: float, time_key: str = "now", model: str = "best_match"):
        return {
            "temperature_2m_c": 24,
            "relative_humidity_2m_pct": 52,
            "wind_speed_10m_kmh": 8,
            "wind_gusts_10m_kmh": 13,
            "precipitation_mm": 0,
            "vapour_pressure_deficit_kpa": 1.4,
            "soil_moisture_1_to_3cm_m3m3": 0.20,
            "soil_temperature_6cm_c": 20,
        }

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_fetch)
    result = await weather.weather_operation_tile_data(
        5, 16, 14, operation="spraying", time="now", model="best_match", interpolation="grid"
    )

    assert result["layer"] == "operation_spraying"
    assert result["interpolation"]["point_count"] == 5
    assert all(0 <= p["value"] <= 1 for p in result["interpolation"]["points"])


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
