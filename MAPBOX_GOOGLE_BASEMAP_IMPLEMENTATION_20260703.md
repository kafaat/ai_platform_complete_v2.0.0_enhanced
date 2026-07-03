# Sahool Mapbox / Google Basemap Implementation — 2026-07-03

## Scope
Implemented a safe basemap extension for the frontend map stack:

- Keep Esri World Imagery as default free/safe satellite basemap.
- Add Mapbox Satellite Streets as an optional basemap, shown only when `VITE_MAPBOX_TOKEN` is configured.
- Document Google Satellite as an official-only future integration path, explicitly disabled to prevent use of unofficial Google tile URLs.
- Wire the same token-gated basemap logic into Add Field, MapHub Leaflet, and MapHubGL.

## Files changed

- `frontend/src/lib/layerRegistry.ts`
  - Added metadata fields: `attribution`, `maxZoom`, `requiresToken`, `tokenEnv`, `disabled`, `disabledReason`.
  - Added `mapbox-satellite` basemap.
  - Added disabled `google-satellite-official` placeholder.
  - Added `resolveLayerSource()` and `availableBasemapLayers()` helpers.

- `frontend/src/components/AddFieldWithMap.tsx`
  - Replaced binary street/satellite toggle with a basemap selector.
  - Uses `availableBasemapLayers(import.meta.env)`.
  - Mapbox appears only with `VITE_MAPBOX_TOKEN`.
  - Basemap attribution and maxZoom now come from the registry.

- `frontend/src/components/maphub/HubMap.tsx`
  - Resolves token-gated basemap URLs through `resolveLayerSource()`.
  - Uses registry attribution and maxZoom.

- `frontend/src/components/maphub/HubMapGL.tsx`
  - Resolves token-gated basemap URLs through `resolveLayerSource()` for MapLibre raster source.
  - Uses registry attribution.

- `frontend/src/sections/MapHub.tsx`
  - Filters basemaps via `availableBasemapLayers(import.meta.env)` so unavailable Mapbox/disabled Google do not appear.

- `frontend/src/lib/layerRegistry.test.ts`
  - Updated tests for expanded basemap/index registry.

- `tests_v9/test_mapbox_basemap_contract_20260703.py`
  - Added static CI guard for Mapbox/Google basemap contract.

## Runtime config

To enable Mapbox in the UI:

```env
VITE_MAPBOX_TOKEN=<your-mapbox-public-token>
```

Without this token, the UI shows only the safe built-in basemaps:

- Esri World Imagery
- CARTO Light

Google is intentionally not active. Use Google only through the official Google Map Tiles API/session flow in a future dedicated integration; do not use unofficial `mt.google.com/vt/...` tile URLs.

## Verification

Executed:

```bash
python scripts/ci/v9_gpu_contract_gate.py
python scripts/ci/v9_feature_transfer_gate.py
python scripts/ci/service_port_gate.py
python -m pytest -q \
  tests_v9/test_mapbox_basemap_contract_20260703.py \
  tests_v9/test_segmentation_frontend_contract_20260702.py \
  tests_v9/test_frontend_nginx_service_proxy_guard.py \
  tests_v9/test_v9_gpu_enablement_20260702.py
bash scripts/production_validation_gate.sh
```

Results:

- `v9-gpu-contract-gate: PASS`
- `v9-feature-transfer-gate: PASS`
- `service-port-gate: PASS`
- Focused tests: `19 passed`
- Production validation gate: `passed`
- Python compile sweep: `compiled=1642 failed=0`
- Compose parse: `docker-compose.v9.yml parsed; services=53`
