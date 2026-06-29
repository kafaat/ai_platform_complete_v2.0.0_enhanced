# WEATHER ENGINE V20 — Readiness + Self-Test Hardening

## Scope
This phase continues from v19 and adds production-facing local health/readiness probes for the SAHOOL weather engine without calling Open-Meteo during readiness checks.

## Implemented

### Backend endpoints
Added to `services/sahool-platform/api/routers/weather.py`:

- `GET /api/v1/weather/readyz`
  - Production readiness endpoint for Docker/Kubernetes/API gateway routing.
  - Does not call Open-Meteo.
  - Returns HTTP 200 when local checks pass and Open-Meteo circuit breaker is closed.
  - Returns HTTP 503 when local checks fail or the Open-Meteo breaker is open/tripped.

- `GET /api/v1/weather/self-test`
  - Local dry-run diagnostics for the weather engine.
  - Validates tile center math, configured layers/times, operation suitability engine, Prometheus exporter, and cache accounting.
  - Does not call Open-Meteo.

### Manifest update
Updated `GET /api/v1/weather/layers` to advertise:

- `/api/v1/weather/health`
- `/api/v1/weather/readyz`
- `/api/v1/weather/self-test`
- `/api/v1/weather/tile-cache/stats`
- `/api/v1/weather/tile-cache/prune`
- `/api/v1/weather/observability`
- `/api/v1/weather/metrics.prom`

### Internal helpers
Added:

- `_weather_engine_self_checks()`
- `_weather_runtime_readiness()`

These helpers keep readiness logic deterministic and avoid external I/O.

## Tests added

Added:

`services/sahool-platform/tests/test_weather_engine_v20_readiness_selftest.py`

Coverage:

- Manifest advertises readiness/self-test endpoints.
- Self-test passes without external I/O.
- Readiness returns ready when local checks pass and breaker is closed.
- Readiness degrades with HTTP 503 when breaker is open.

## Verification performed

### Backend compile

```bash
python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core
```

Result: passed.

### Weather backend tests

```bash
PYTHONPATH=services/sahool-platform python3 -m pytest -q \
  services/sahool-platform/tests/test_weather_tile_engine_v10.py \
  services/sahool-platform/tests/test_weather_engine_v11_windows.py \
  services/sahool-platform/tests/test_weather_engine_v12_operation_plan.py \
  services/sahool-platform/tests/test_weather_engine_v18_observability.py \
  services/sahool-platform/tests/test_weather_engine_v19_prometheus_cache_admin.py \
  services/sahool-platform/tests/test_weather_engine_v20_readiness_selftest.py
```

Result: `22 passed`.

### Frontend build

```bash
cd frontend
npm ci
npm run typecheck
npm run build
npm test -- src/components/maphub/weather/WeatherEngine.static.test.ts
```

Result:

- TypeScript passed.
- Vite production build passed.
- Weather static test passed: `4 passed`.

## Notes

- `frontend/dist/` was regenerated.
- `frontend/node_modules/` is intentionally excluded from the final package.
- Readiness intentionally avoids upstream calls to prevent quota burn, network flakiness, and cascading failures.
