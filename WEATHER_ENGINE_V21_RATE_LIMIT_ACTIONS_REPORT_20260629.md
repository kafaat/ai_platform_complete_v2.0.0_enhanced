# SAHOOL Weather Engine V21 — Rate Limiting + Task/Recommendation Bridge

## Scope
Implemented the two requested remaining stages:

6. Weather endpoint rate limiting and request-budget protection.
7. Weather-driven task and recommendation integration from Operation Plan.

## Backend changes

### Rate limiting
Added an in-process rate limiter for high-traffic weather endpoints:

- `tile-data`
- `operation-tile-data`
- `tile-series`
- `probe`
- `operation-window`
- `operation-plan`
- `field-weather-summary`
- `weather-action-recommendation`
- `task-from-operation-plan`
- `recommendation-from-operation-plan`

The limiter keys by Authorization token hash when present, otherwise tenant header + client IP. It returns HTTP `429` with `Retry-After` on exhaustion.

The manifest now exposes the active policy through:

```http
GET /api/v1/weather/layers
```

and metrics expose:

```text
sahool_weather_rate_limited_total{endpoint="..."}
```

### Action recommendation bridge
Added:

```http
GET /api/v1/weather/action-recommendation
```

This returns a unified operation plan, a recommendation payload, and a ready task draft without writing to DB.

### Create task from weather plan
Added:

```http
POST /api/v1/weather/tasks/from-operation-plan
```

- `dry_run=true`: returns the task draft only.
- `dry_run=false`: writes a row into `field_tasks` and emits `TASK_CREATED`.
- Uses `FIELD_EDIT` permission.

### Save weather recommendation
Added:

```http
POST /api/v1/weather/recommendations/from-operation-plan
```

- `dry_run=true`: returns the recommendation payload only.
- `dry_run=false`: writes into `recommendations` and emits `RECOMMENDATION_CREATED`.
- Uses `RECOMMENDATION_REQUEST` permission.

## Frontend changes

Updated the MapHub weather probe popup:

- The selected field id is passed into the weather marker.
- The popup fetches `/api/v1/weather/action-recommendation`.
- It shows a task draft generated from the best weather window.
- It provides buttons to:
  - create a task from the best window.
  - save the weather decision as a recommendation.

Modified files:

```text
services/sahool-platform/api/routers/weather.py
services/sahool-platform/tests/test_weather_engine_v21_rate_limit_actions.py
frontend/src/components/maphub/OverlayMarkers.tsx
frontend/src/components/maphub/weather/WeatherRasterOverlay.tsx
frontend/src/components/maphub/weather/WeatherProbePopup.ts
frontend/src/sections/MapHub.tsx
```

## Verification

Backend tests:

```bash
PYTHONPATH=services/sahool-platform python3 -m pytest -q \
  services/sahool-platform/tests/test_weather_tile_engine_v10.py \
  services/sahool-platform/tests/test_weather_engine_v11_windows.py \
  services/sahool-platform/tests/test_weather_engine_v12_operation_plan.py \
  services/sahool-platform/tests/test_weather_engine_v18_observability.py \
  services/sahool-platform/tests/test_weather_engine_v19_prometheus_cache_admin.py \
  services/sahool-platform/tests/test_weather_engine_v20_readiness_selftest.py \
  services/sahool-platform/tests/test_weather_engine_v21_rate_limit_actions.py
```

Result:

```text
26 passed
```

Python compile:

```bash
python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core
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
WeatherEngine.static.test.ts: 4 passed
```

## Notes

`frontend/node_modules` is intentionally excluded from the final package.
