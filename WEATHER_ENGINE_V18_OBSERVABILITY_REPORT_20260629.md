# SAHOOL Weather Engine V18 — Observability & Remaining Phase Continuation

## Summary
This phase continues from `sahool_v17.zip` and adds lightweight operational observability to the Open-Meteo/SAHOOL weather engine while preserving the main-synced codebase.

## Added backend capabilities

### New endpoint

```http
GET /api/v1/weather/observability
```

Returns:
- weather-engine identity
- source/rendering ownership
- cache snapshot
- endpoint request counters
- cache-state counters
- upstream served/error counters
- layer usage counters
- operation usage counters

### Existing endpoint strengthened

```http
GET /api/v1/weather/tile-cache/stats
```

Now reuses one internal cache snapshot helper and reports:
- `items`
- `fresh_items`
- `stale_items`
- `expired_items`
- `ttl_s`
- `stale_ttl_s`
- `max_items_soft`

### Manifest updated

`GET /api/v1/weather/layers` now advertises:

```json
"observability_endpoints": [
  "/api/v1/weather/tile-cache/stats",
  "/api/v1/weather/observability"
]
```

## Instrumented paths

The following paths now increment lightweight counters:

- `/api/v1/weather/tile-data/{z}/{x}/{y}`
- `/api/v1/weather/operation-tile-data/{z}/{x}/{y}`
- `/api/v1/weather/probe`
- `/api/v1/weather/operation-window`
- `/api/v1/weather/field-weather-summary`
- `/api/v1/weather/operation-plan`
- `/api/v1/weather/tile-series/{z}/{x}/{y}`

## Tests added

Added:

```text
services/sahool-platform/tests/test_weather_engine_v18_observability.py
```

Coverage:
- manifest advertises observability endpoints
- tile-data increments request/layer/cache metrics
- operation-plan increments request/operation metrics

## Verification

Backend compile:

```bash
python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core
```

Weather test suite:

```bash
PYTHONPATH=services/sahool-platform python3 -m pytest -q \
  services/sahool-platform/tests/test_weather_tile_engine_v10.py \
  services/sahool-platform/tests/test_weather_engine_v11_windows.py \
  services/sahool-platform/tests/test_weather_engine_v12_operation_plan.py \
  services/sahool-platform/tests/test_weather_engine_v18_observability.py
```

Result:

```text
14 passed
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
typecheck passed
Vite production build passed
WeatherEngine.static.test.ts: 4 passed
```

## Notes

`frontend/node_modules` is intentionally excluded from the release zip to keep the package practical for mobile download and sharing.
