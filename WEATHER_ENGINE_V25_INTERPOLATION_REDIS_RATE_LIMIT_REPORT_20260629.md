# SAHOOL Weather Engine V25 — Spatial Interpolation + Redis-backed Rate Limiting

## Scope

This phase implements the requested remaining phases:

1. **Spatial interpolation inside weather tiles** for smoother SAHOOL-rendered weather/wind/operation layers.
2. **Stronger multi-tenant rate limiting** with Redis-backed runtime support, safe memory fallback, and standard rate-limit headers.

## Backend changes

Updated:

```text
services/sahool-platform/api/routers/weather.py
```

### Spatial interpolation

Added optional query parameter to tile endpoints:

```http
GET /api/v1/weather/tile-data/{z}/{x}/{y}?interpolation=center|grid
GET /api/v1/weather/operation-tile-data/{z}/{x}/{y}?interpolation=center|grid
```

`center` preserves legacy behavior and keeps existing tests stable.

`grid` returns a 2x2+center payload:

```json
{
  "interpolation": {
    "mode": "bilinear_2x2_center",
    "quality": "smooth",
    "point_count": 5,
    "average_value": 25.4,
    "points": [
      {"id":"nw","u":0.18,"v":0.18,"value":25.1},
      {"id":"ne","u":0.82,"v":0.18,"value":25.5},
      {"id":"sw","u":0.18,"v":0.82,"value":25.2},
      {"id":"se","u":0.82,"v":0.82,"value":25.8},
      {"id":"center","u":0.50,"v":0.50,"value":25.4}
    ]
  }
}
```

The interpolation path uses the existing weather cache and stale fallback path for each point.

### Redis-backed rate limiting

Added rate limiter backend configuration:

```bash
SAHOOL_WEATHER_RATE_LIMIT_BACKEND=redis
SAHOOL_WEATHER_RATE_LIMIT_REDIS_URL=redis://redis:6379/0
SAHOOL_WEATHER_RATE_LIMIT_REDIS_FALLBACK_MEMORY=1
```

The limiter now supports:

- tenant/user/IP-scoped keys;
- Redis `INCR`/`EXPIRE` fixed-window enforcement;
- memory fallback when Redis is unavailable and fallback is enabled;
- hard 429 when Redis is required but unavailable;
- response headers:
  - `X-RateLimit-Limit`
  - `X-RateLimit-Remaining`
  - `X-RateLimit-Reset`
  - `X-RateLimit-Backend`
  - `Retry-After` on 429.

Added endpoint:

```http
GET /api/v1/weather/rate-limit/backend
```

Added Prometheus metric:

```text
sahool_weather_rate_limit_backend_total
```

Updated manifest:

```http
GET /api/v1/weather/layers
```

Now advertises:

- `tile_interpolation`;
- rate limit `backend` and `policies`;
- `/api/v1/weather/rate-limit/backend`.

## Frontend changes

Updated:

```text
frontend/src/components/maphub/weather/weatherLayerDefinitions.ts
frontend/src/components/maphub/weather/WeatherTileLayer.ts
frontend/src/components/maphub/weather/WeatherEngine.static.test.ts
```

MapHub weather tiles now request:

```text
interpolation=grid
```

The SVG renderer uses interpolation points to render corner-aware soft gradients over the tile. Legacy fallback rendering remains available when interpolation is missing.

## Tests

Added:

```text
services/sahool-platform/tests/test_weather_engine_v25_interpolation_rate_redis.py
```

It covers:

- weather tile grid interpolation;
- operation tile grid interpolation;
- Redis-backed rate limiter headers and 429 behavior;
- manifest and Prometheus exposure.

## Verification executed

Backend:

```bash
python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core
PYTHONPATH=services/sahool-platform python3 -m pytest -q \
  services/sahool-platform/tests/test_weather_tile_engine_v10.py \
  services/sahool-platform/tests/test_weather_engine_v11_windows.py \
  services/sahool-platform/tests/test_weather_engine_v12_operation_plan.py \
  services/sahool-platform/tests/test_weather_engine_v18_observability.py \
  services/sahool-platform/tests/test_weather_engine_v19_prometheus_cache_admin.py \
  services/sahool-platform/tests/test_weather_engine_v20_readiness_selftest.py \
  services/sahool-platform/tests/test_weather_engine_v21_rate_limit_actions.py \
  services/sahool-platform/tests/test_weather_engine_v22_runtime_contract.py \
  services/sahool-platform/tests/test_weather_engine_v24_redis_ready_cache.py \
  services/sahool-platform/tests/test_weather_engine_v25_interpolation_rate_redis.py
```

Result:

```text
38 passed
```

Frontend:

```bash
cd frontend
npm ci
npm run typecheck
npm run build
npm test -- src/components/maphub/weather/WeatherEngine.static.test.ts
```

Result:

```text
TypeScript passed
Vite production build passed
WeatherEngine.static.test.ts: 5 passed
```

## Notes

- `frontend/node_modules` is intentionally excluded from the final archive.
- Docker/Compose runtime verification is still not claimed in this phase.
