# WEATHER ENGINE V24 — Redis-ready Weather Cache

## Scope

This phase makes the SAHOOL Weather Engine cache Redis-ready while preserving the current in-memory behavior for local development and tests.

## Added

- Optional runtime cache backend selection:
  - `SAHOOL_WEATHER_CACHE_BACKEND=memory` default.
  - `SAHOOL_WEATHER_CACHE_BACKEND=redis` for production.
- Optional Redis URL discovery:
  - `SAHOOL_WEATHER_REDIS_URL`
  - `WEATHER_REDIS_URL`
  - `REDIS_URL`
- Safe memory fallback:
  - `SAHOOL_WEATHER_REDIS_FALLBACK_MEMORY=1` default.
- Endpoint:
  - `GET /api/v1/weather/tile-cache/backend`
- Prometheus counter:
  - `sahool_weather_cache_backend_total`
- Redis key prefix:
  - `sahool:weather:tile:*`

## Behavior

The existing cache semantics are preserved:

1. Fresh cache.
2. Refresh from Open-Meteo.
3. Stale fallback.
4. Clear upstream error only when no usable cached value exists.

When Redis is enabled, Redis stores weather samples through `setex` using the stale TTL. If Redis is unavailable and fallback is enabled, the engine continues using memory cache.

## Verification

Added test file:

`services/sahool-platform/tests/test_weather_engine_v24_redis_ready_cache.py`

Coverage:

- Default memory backend.
- Fake Redis backend get/set path.
- Redis missing URL fallback to memory.
- Manifest and Prometheus exposure.

## Notes

No hard Redis dependency was added. The implementation imports `redis.asyncio` lazily only when Redis backend is selected.
