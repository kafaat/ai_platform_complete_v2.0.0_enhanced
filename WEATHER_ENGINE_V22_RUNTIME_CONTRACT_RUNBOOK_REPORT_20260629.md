# WEATHER ENGINE V22 — Runtime Contract + Runbook

## Implemented phases

### Phase 1 — Runtime contract verification
Added local-only runtime contract checks for the weather engine:

- `GET /api/v1/weather/runtime-contract`
- Verifies weather API route registration.
- Verifies rate-limit/cache/metrics/action bridge guards.
- Exposes the frontend integration contract for MapHub weather modules.
- Does not call Open-Meteo or the database.

### Phase 2 — Operational guardrails/runbook
Added local operational checks and runbook:

- `GET /api/v1/weather/env-doctor`
- `docs/runbooks/WEATHER_ENGINE_RUNBOOK.md`
- Validates cache TTLs, rate-limit policy, action endpoint guardrails, readiness, metrics, and runtime contract status.

## Frontend static runtime coverage
Enhanced:

- `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts`

Coverage now includes the weather action bridge buttons and endpoints:

- `/api/v1/weather/action-recommendation`
- `/api/v1/weather/tasks/from-operation-plan`
- `/api/v1/weather/recommendations/from-operation-plan`
- Create task button
- Save recommendation button

## Backend tests
Added:

- `services/sahool-platform/tests/test_weather_engine_v22_runtime_contract.py`

## Verification

```bash
PYTHONPATH=services/sahool-platform python3 -m pytest -q \
  services/sahool-platform/tests/test_weather_tile_engine_v10.py \
  services/sahool-platform/tests/test_weather_engine_v11_windows.py \
  services/sahool-platform/tests/test_weather_engine_v12_operation_plan.py \
  services/sahool-platform/tests/test_weather_engine_v18_observability.py \
  services/sahool-platform/tests/test_weather_engine_v19_prometheus_cache_admin.py \
  services/sahool-platform/tests/test_weather_engine_v20_readiness_selftest.py \
  services/sahool-platform/tests/test_weather_engine_v21_rate_limit_actions.py \
  services/sahool-platform/tests/test_weather_engine_v22_runtime_contract.py
```

Result:

```text
30 passed
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
`frontend/node_modules` is intentionally not included in the release archive.
