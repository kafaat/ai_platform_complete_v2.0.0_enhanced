# SAHOOL Weather Engine V26 — Runtime Smoke + Frontend E2E Contract

## Scope

This phase adds two production-oriented layers on top of V25:

1. **Runtime smoke verification** for Docker/Compose/Kubernetes/API Gateway deployments.
2. **Frontend MapHub Weather E2E contract** with mocked weather APIs, so CI can verify the weather UI flow without Open-Meteo or database access.

## Backend changes

Updated:

```text
services/sahool-platform/api/routers/weather.py
```

### New endpoint

```http
GET /api/v1/weather/runtime-smoke-plan
```

This endpoint returns an operator-ready smoke checklist with:

- critical control-plane endpoints;
- expected HTTP statuses;
- real tile and operation-plan sample endpoints;
- MapHub weather route to open for visual verification;
- commands for runtime smoke, frontend build, and Playwright smoke.

The endpoint is local-only and does not call Open-Meteo or the database.

### Manifest and runtime contract updates

Updated:

```http
GET /api/v1/weather/layers
GET /api/v1/weather/runtime-contract
GET /api/v1/weather/env-doctor
```

They now include `/api/v1/weather/runtime-smoke-plan` as an operational endpoint.

## Runtime smoke CLI

Added:

```text
scripts/weather_runtime_smoke.py
```

Usage:

```bash
python3 scripts/weather_runtime_smoke.py --base-url http://localhost:8000
```

It checks:

- `/api/v1/weather/readyz`
- `/api/v1/weather/self-test`
- `/api/v1/weather/runtime-contract`
- `/api/v1/weather/env-doctor`
- `/api/v1/weather/runtime-smoke-plan`
- `/api/v1/weather/layers`
- `/api/v1/weather/tile-cache/stats`
- `/api/v1/weather/observability`
- `/api/v1/weather/metrics.prom`

Optional external/upstream-sensitive checks:

```bash
python3 scripts/weather_runtime_smoke.py --base-url http://localhost:8000 --include-external
```

## Frontend E2E smoke contract

Added:

```text
frontend/e2e/weather-maphub-smoke.spec.ts
```

Updated:

```text
frontend/package.json
```

New script:

```bash
npm run e2e:weather-smoke
```

The Playwright spec mocks weather APIs and validates the MapHub weather contract:

- weather manifest loading;
- tile requests using `interpolation=grid`;
- probe/action recommendation endpoint contract;
- task/recommendation action endpoints;
- no browser console crash during the mocked flow.

## Backend tests

Added:

```text
services/sahool-platform/tests/test_weather_engine_v26_runtime_smoke_assets.py
```

Executed:

```bash
python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core
PYTHONPATH=services/sahool-platform python3 -m pytest -vv \
  services/sahool-platform/tests/test_weather_tile_engine_v10.py \
  services/sahool-platform/tests/test_weather_engine_v11_windows.py \
  services/sahool-platform/tests/test_weather_engine_v12_operation_plan.py \
  services/sahool-platform/tests/test_weather_engine_v18_observability.py \
  services/sahool-platform/tests/test_weather_engine_v19_prometheus_cache_admin.py \
  services/sahool-platform/tests/test_weather_engine_v20_readiness_selftest.py \
  services/sahool-platform/tests/test_weather_engine_v21_rate_limit_actions.py \
  services/sahool-platform/tests/test_weather_engine_v22_runtime_contract.py \
  services/sahool-platform/tests/test_weather_engine_v24_redis_ready_cache.py \
  services/sahool-platform/tests/test_weather_engine_v25_interpolation_rate_redis.py \
  services/sahool-platform/tests/test_weather_engine_v26_runtime_smoke_assets.py
```

Result:

```text
43 passed
```

## Frontend verification

Executed:

```bash
cd frontend
npm ci
npm run build
npm test -- src/components/maphub/weather/WeatherEngine.static.test.ts
```

Result:

```text
Vite production build passed
WeatherEngine.static.test.ts: 5 passed
```

Attempted:

```bash
npm run typecheck
```

Result: did not complete within the execution timeout in this environment. The production Vite build completed successfully.

Attempted:

```bash
npm run e2e:weather-smoke -- --project=chromium
```

Result: could not run because the Playwright Chromium browser binary is not installed in the container. The test file is included and ready to run after:

```bash
cd frontend
npx playwright install chromium
npm run e2e:weather-smoke -- --project=chromium
```

## Packaging notes

- `frontend/dist` is included.
- `frontend/node_modules` is excluded.
- Playwright `test-results` are excluded from the final archive.
- Docker/Compose live runtime was not started in this phase.
