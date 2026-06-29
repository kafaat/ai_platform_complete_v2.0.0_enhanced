# SAHOOL Weather Engine V19 — Prometheus Metrics + Cache Admin

Date: 2026-06-29
Base: `sahool_v18.zip`
Output: `sahool_v19.zip`

## Scope

This phase continues the remaining production-readiness work for the Open-Meteo/SAHOOL weather engine by adding lightweight operational metrics and cache administration endpoints without introducing mandatory Prometheus or Redis dependencies.

## Implemented

### 1. Prometheus-compatible metrics endpoint

Added:

```http
GET /api/v1/weather/metrics.prom
```

The endpoint returns `text/plain; version=0.0.4` metrics for:

- `sahool_weather_cache_items`
- `sahool_weather_cache_ttl_seconds`
- `sahool_weather_requests_total`
- `sahool_weather_cache_states_total`
- `sahool_weather_upstream_total`
- `sahool_weather_layers_total`
- `sahool_weather_operations_total`

This allows Prometheus/Grafana or simple curl checks to observe the weather runtime without requiring the `prometheus_client` package.

### 2. Cache prune endpoint

Added:

```http
POST /api/v1/weather/tile-cache/prune?expired_only=true
```

Behavior:

- `expired_only=true`: removes entries older than stale TTL only.
- `expired_only=false`: removes entries older than the fresh TTL, including stale entries.

The response includes before/after/removed counts and a fresh cache snapshot.

### 3. Manifest update

Updated:

```http
GET /api/v1/weather/layers
```

The `observability_endpoints` list now includes:

```text
/api/v1/weather/tile-cache/stats
/api/v1/weather/tile-cache/prune
/api/v1/weather/observability
/api/v1/weather/metrics.prom
```

### 4. Tests

Added:

```text
services/sahool-platform/tests/test_weather_engine_v19_prometheus_cache_admin.py
```

Coverage:

- Manifest advertises Prometheus and prune endpoints.
- Prometheus metrics export includes request/layer/cache counters.
- Cache prune removes expired entries only.
- Cache prune can remove stale entries when requested.

## Verification

Backend tests:

```bash
PYTHONPATH=services/sahool-platform python3 -m pytest -q \
  services/sahool-platform/tests/test_weather_tile_engine_v10.py \
  services/sahool-platform/tests/test_weather_engine_v11_windows.py \
  services/sahool-platform/tests/test_weather_engine_v12_operation_plan.py \
  services/sahool-platform/tests/test_weather_engine_v18_observability.py \
  services/sahool-platform/tests/test_weather_engine_v19_prometheus_cache_admin.py
```

Result:

```text
18 passed
```

Python compile check:

```bash
python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core
```

Result: passed.

Frontend verification:

```bash
cd frontend
npm ci
npm run typecheck
npm run build
npm test -- src/components/maphub/weather/WeatherEngine.static.test.ts
```

Result:

```text
typecheck passed
Vite production build passed
WeatherEngine.static.test.ts: 4 passed
```

## Notes

- `frontend/node_modules` is not included in the release archive.
- `frontend/dist` is regenerated and included.
- No external network call is needed by the new observability endpoints.
