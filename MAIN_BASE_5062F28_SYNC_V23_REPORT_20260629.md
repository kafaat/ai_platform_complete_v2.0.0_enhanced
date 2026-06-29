# SAHOOL v23 — Main Base 5062f28 Weather Engine Sync

## Base

The attached `sahool_platform_5062f28.zip` was treated as the authoritative base synchronized with `main`.

## Scope

This update synchronized the missing Weather Engine phases from the validated v22 line into the new main-synchronized base without replacing unrelated modules.

## Added/Synchronized

### Backend

- `services/sahool-platform/api/routers/weather.py`

The synchronized router includes:

- Open-Meteo tile data API
- operation tile data
- weather probe
- tile series
- operation window
- field weather summary
- operation plan
- rate limiting
- action recommendation bridge
- task creation bridge from operation plan
- recommendation save bridge from operation plan
- cache stats and prune
- observability
- Prometheus metrics
- readiness
- self-test
- runtime contract
- env doctor

### Frontend Weather Components

- `frontend/src/components/maphub/weather/WeatherRasterOverlay.tsx`
- `frontend/src/components/maphub/weather/WeatherTileLayer.ts`
- `frontend/src/components/maphub/weather/WeatherLayerPanel.ts`
- `frontend/src/components/maphub/weather/WeatherProbePopup.ts`
- `frontend/src/components/maphub/weather/weatherLayerDefinitions.ts`
- `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts`
- `frontend/src/components/maphub/OverlayMarkers.tsx`
- `frontend/src/sections/MapHub.tsx`

### Tests

- `test_weather_tile_engine_v10.py`
- `test_weather_engine_v11_windows.py`
- `test_weather_engine_v12_operation_plan.py`
- `test_weather_engine_v18_observability.py`
- `test_weather_engine_v19_prometheus_cache_admin.py`
- `test_weather_engine_v20_readiness_selftest.py`
- `test_weather_engine_v21_rate_limit_actions.py`
- `test_weather_engine_v22_runtime_contract.py`

### Documentation

- `docs/runbooks/WEATHER_ENGINE_RUNBOOK.md`
- `WEATHER_ENGINE_V21_RATE_LIMIT_ACTIONS_REPORT_20260629.md`
- `WEATHER_ENGINE_V22_RUNTIME_CONTRACT_RUNBOOK_REPORT_20260629.md`

## Verification

### Python compile

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
  services/sahool-platform/tests/test_weather_engine_v20_readiness_selftest.py \
  services/sahool-platform/tests/test_weather_engine_v21_rate_limit_actions.py \
  services/sahool-platform/tests/test_weather_engine_v22_runtime_contract.py
```

Result: `30 passed`.

### Frontend

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
- Weather static test passed: `5 passed`.

## Notes

- `frontend/node_modules` is intentionally excluded from the final archive.
- The generated `frontend/dist` is included.
- The new base was preserved as the source of truth; only the Weather Engine missing phases and their direct integration files were synchronized.
