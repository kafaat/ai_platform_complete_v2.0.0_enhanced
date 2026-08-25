from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

main = importlib.import_module("main")
cache = importlib.import_module("cache")


def test_readyz_reports_ready_when_open_meteo_probe_succeeds(monkeypatch):
    async def ok_probe():
        return {"ok": True, "provider": "open-meteo", "time": "2026-07-09T12:00"}

    monkeypatch.setattr(main, "readiness_probe", ok_probe)
    client = TestClient(main.app)
    payload = client.get("/readyz").json()
    assert payload["status"] == "ready"
    assert payload["upstream_open_meteo"]["ok"] is True
    assert payload["cache"]["backend"] in {"memory", "redis"}
    assert payload["circuit_breaker"]["provider"] == "open-meteo"


def test_readyz_reports_degraded_when_open_meteo_probe_fails(monkeypatch):
    async def bad_probe():
        return {"ok": False, "provider": "open-meteo", "error": "circuit breaker is open"}

    monkeypatch.setattr(main, "readiness_probe", bad_probe)
    client = TestClient(main.app)
    response = client.get("/readyz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["upstream_open_meteo"]["ok"] is False


def test_cache_falls_back_to_memory_when_redis_is_configured_but_unavailable(monkeypatch):
    class FailingRedis:
        @classmethod
        def from_url(cls, *_args, **_kwargs):
            raise RuntimeError("redis unavailable")

    class RedisModule:
        Redis = FailingRedis

    monkeypatch.setitem(sys.modules, "redis", RedisModule)
    monkeypatch.setattr(cache, "REDIS_URL", "redis://does-not-exist:6379/0")
    monkeypatch.setattr(cache, "_REDIS_CLIENT", None)
    monkeypatch.setattr(cache, "_REDIS_ERROR", None)
    cache._CACHE.clear()

    cache.set("k", {"value": 7})
    value, state, _age = cache.get("k")
    stats = cache.stats()

    assert value == {"value": 7}
    assert state == "fresh"
    assert stats["backend"] == "memory"
    assert stats["redis_configured"] is True
    assert "redis unavailable" in stats["redis_error"]


def test_cache_uses_redis_backend_when_available(monkeypatch):
    class FakeRedisClient:
        store: dict[str, str] = {}
        ttls: dict[str, int] = {}

        def ping(self):
            return True

        def get(self, key: str):
            return self.store.get(key)

        def setex(self, key: str, ttl: int, value: str):
            self.store[key] = value
            self.ttls[key] = ttl
            return True

        def ttl(self, key: str):
            # عدّادُ الخادم: كامل المدّة فور الكتابة ⇒ عمرٌ صفر بحقّ لا بالتلفيق.
            return self.ttls.get(key, -2)

    class FakeRedisFactory:
        @classmethod
        def from_url(cls, *_args, **_kwargs):
            return FakeRedisClient()

    class RedisModule:
        Redis = FakeRedisFactory

    monkeypatch.setitem(sys.modules, "redis", RedisModule)
    monkeypatch.setattr(cache, "REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setattr(cache, "_REDIS_CLIENT", None)
    monkeypatch.setattr(cache, "_REDIS_ERROR", None)
    cache._CACHE.clear()

    cache.set("redis-key", {"temperature_c": 28.5})
    value, state, age = cache.get("redis-key")
    stats = cache.stats()

    assert value == {"temperature_c": 28.5}
    assert state == "fresh"
    assert age == 0
    assert stats["backend"] == "redis"
    assert stats["redis_configured"] is True
