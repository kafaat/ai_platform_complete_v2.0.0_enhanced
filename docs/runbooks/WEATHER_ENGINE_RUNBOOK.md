# SAHOOL Weather Engine Runbook

## Scope
This runbook covers the SAHOOL weather map layer where Open-Meteo provides data and SAHOOL renders map tiles, wind animation, legends, probes, operation plans, task drafts, and recommendation drafts.

## Core runtime checks
Run these after deployment or after changing weather code:

```bash
curl -fsS http://localhost:8000/api/v1/weather/readyz
curl -fsS http://localhost:8000/api/v1/weather/self-test
curl -fsS http://localhost:8000/api/v1/weather/runtime-contract
curl -fsS http://localhost:8000/api/v1/weather/env-doctor
curl -fsS http://localhost:8000/api/v1/weather/layers
```

Expected status: `readyz.status=ready`, `self-test.status=ok`, `runtime-contract.status=ok`, `env-doctor.status=ok`.

## Observability
Prometheus/OpenMetrics endpoint:

```bash
curl -fsS http://localhost:8000/api/v1/weather/metrics.prom
```

Human-readable operational endpoint:

```bash
curl -fsS http://localhost:8000/api/v1/weather/observability
```

Cache status:

```bash
curl -fsS http://localhost:8000/api/v1/weather/tile-cache/stats
```

Clean expired cache entries:

```bash
curl -X POST 'http://localhost:8000/api/v1/weather/tile-cache/prune?expired_only=true'
```

## Frontend smoke flow
1. Open MapHub.
2. Enable the weather layer.
3. Switch layer to wind, temperature, and an operation layer.
4. Click on the map and confirm that the probe popup shows:
   - weather probe
   - operation window
   - operation plan
   - action recommendation
   - create task button
   - save recommendation button

## Rate limiting
The weather engine includes in-process rate limits for high-volume tile/probe/action endpoints. A rejected request returns `429` with `Retry-After`.

The current policy is exposed in:

```bash
curl -fsS http://localhost:8000/api/v1/weather/layers | jq .rate_limits
```

## Action bridge
Dry-run before writing anything:

```bash
curl -fsS 'http://localhost:8000/api/v1/weather/action-recommendation?lat=15&lon=45&field_id=demo-field&operations=spraying,irrigation&hours=0,3,6&model=best_match'
```

Task and recommendation creation endpoints require field-edit permission in non-dry-run mode:

```http
POST /api/v1/weather/tasks/from-operation-plan
POST /api/v1/weather/recommendations/from-operation-plan
```

## Known production caveat
The current rate limit and weather tile cache are in-process. For multi-replica production, migrate to Redis to share cache and quotas across containers.

## V24 — Redis-ready Weather Cache

Local/default mode uses in-process memory cache:

```bash
curl -s http://localhost:8000/api/v1/weather/tile-cache/backend
```

Production can enable Redis without changing the API contract:

```bash
export SAHOOL_WEATHER_CACHE_BACKEND=redis
export SAHOOL_WEATHER_REDIS_URL=redis://redis:6379/0
export SAHOOL_WEATHER_REDIS_FALLBACK_MEMORY=1
```

Expected properties:

- Redis is optional; local development continues to use memory.
- When Redis is selected but unavailable, memory fallback keeps MapHub weather usable by default.
- Cache entries are stored under the `sahool:weather:tile:*` prefix.
- Redis values use the same fresh/stale semantics as the memory cache.
- `/api/v1/weather/tile-cache/backend` reports the effective mode without exposing the Redis URL.
- Prometheus exports `sahool_weather_cache_backend_total` for backend events.

Operational check:

```bash
curl -s http://localhost:8000/api/v1/weather/env-doctor
curl -s http://localhost:8000/api/v1/weather/metrics.prom | grep sahool_weather_cache_backend_total
```

## V25 — Spatial Interpolation + Redis-backed Rate Limiting

### Smooth tile rendering

The MapHub weather GridLayer requests interpolated tile payloads by appending:

```bash
interpolation=grid
```

Supported API modes:

```text
center  # legacy center-sample payload; lower upstream cost
grid    # 2x2+center payload for smoother SAHOOL SVG rendering
```

Manual checks:

```bash
curl -s "$BASE/api/v1/weather/tile-data/5/16/14?layer=temperature&time=now&model=best_match&interpolation=grid" | jq '.interpolation'
curl -s "$BASE/api/v1/weather/operation-tile-data/5/16/14?operation=spraying&time=now&model=best_match&interpolation=grid" | jq '.interpolation'
```

### Redis-backed rate limiter

Default remains memory mode for local development. Production can enable Redis-backed limits with:

```bash
SAHOOL_WEATHER_RATE_LIMIT_BACKEND=redis
SAHOOL_WEATHER_RATE_LIMIT_REDIS_URL=redis://redis:6379/0
SAHOOL_WEATHER_RATE_LIMIT_REDIS_FALLBACK_MEMORY=1
```

Allowed responses include:

```text
X-RateLimit-Limit
X-RateLimit-Remaining
X-RateLimit-Reset
X-RateLimit-Backend
```

Rejected responses return `429` plus `Retry-After`.

Manual checks:

```bash
curl -i "$BASE/api/v1/weather/tile-data/5/16/14?layer=temperature"
curl -s "$BASE/api/v1/weather/rate-limit/backend" | jq .
curl -s "$BASE/api/v1/weather/metrics.prom" | grep sahool_weather_rate_limit_backend_total
```
