# SAHOOL Weather Engine v16 — Component Split Report

## Summary

This update continues from v15 and finishes the frontend weather-engine refactor into smaller maintainable modules.

Open-Meteo remains the data provider, while SAHOOL owns rendering, animation, legend, layer controls, probe popup, and agronomic operation decisions.

## Files Added

- `frontend/src/components/maphub/weather/WeatherTileLayer.ts`
  - Leaflet GridLayer factory.
  - SVG weather tile rendering.
  - Wind streamline animation rendering.
  - Tile API URL selection for normal weather and operation layers.

- `frontend/src/components/maphub/weather/WeatherLayerPanel.ts`
  - Leaflet weather layer control.
  - Agricultural presets.
  - Time selector.
  - Model selector.
  - Opacity control.
  - Wind animation toggle.
  - Wind density control.
  - Inline legend rendering.

- `frontend/src/components/maphub/weather/WeatherProbePopup.ts`
  - Map click handler.
  - Probe API integration.
  - Operation-window API integration.
  - Operation-plan API integration.
  - Arabic agronomic popup output.

## Files Modified

- `frontend/src/components/maphub/weather/WeatherRasterOverlay.tsx`
  - Reduced from a large monolithic renderer to a small orchestrator component.
  - Delegates tile rendering, control rendering, and probe popup behavior to dedicated modules.

- `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts`
  - Updated to guard the new split architecture and API usage.

## Validation

Executed:

```bash
cd frontend
npm run typecheck
npm run build
```

Expected result:

- TypeScript passes.
- Vite production build passes.
- `frontend/dist` regenerated.

## Notes

This version is a maintainability and production-readiness improvement. It keeps v14/v15 behavior intact while making future additions easier:

- Dynamic backend-driven layer controls.
- Separate CSS/styling migration.
- Performance instrumentation.
- More agricultural layers.
- Redis-backed tile cache integration on the API side.

## Actual Build/Test Results

Executed in this environment:

```bash
cd frontend
npm ci
npm run typecheck
npm run build
npm test -- src/components/maphub/weather/WeatherEngine.static.test.ts
```

Results:

- `npm ci`: passed.
- `npm run typecheck`: passed.
- `npm run build`: passed and regenerated `frontend/dist`.
- Static weather engine test: 1 file passed, 4 tests passed.

## Packaging

`node_modules` was intentionally excluded from the archive. The archive includes source changes, build output under `frontend/dist`, reports, and tests.
