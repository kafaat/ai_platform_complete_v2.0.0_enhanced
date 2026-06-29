# SAHOOL — Field Indicator TileJSON / Tenant Cache / Index Fixes — 2026-06-26

## What was fixed

1. **Stale `_field_layers` tenant cache causing false 403**
   - `_require_field_tenant()` now uses the DB field owner as the source of truth first.
   - If DB confirms the field belongs to the request tenant, stale cached layers with a different tenant are pruned instead of poisoning the request.

2. **Layer authorization DB precedence**
   - `_require_layer_tenant_authorized()` now checks `raster_assets`/DB first when available.
   - Stale in-memory layer tenant metadata is corrected if DB proves ownership.

3. **Index normalization**
   - Added backend normalization for aliases/typos:
     - `NDVU` → `ndvi`
     - `vegetation` → `ndvi`
     - `moisture` → `ndmi`
     - `salinity/salt/soil_salinity` → `ndsi` internally
   - Applied to `tilejson`, `tiles`, `indicator-grid`, `pixel`, and timeseries flows.

4. **Frontend index normalization**
   - Added `normalizeIndicatorIndex()` in `frontend/src/services/api.ts`.
   - `FieldIndicatorMap` normalizes selected index before TileJSON and tile requests.
   - `tid` remains included for browser image tile requests.

5. **Compatibility fallback for misrouted `/api/raster/*`**
   - Added a narrow GET-only passthrough route in `sahool-platform` for environments where old nginx/compose routing accidentally sends `/api/raster/*` to `sahool-platform`.
   - Correct routing remains nginx `/api/raster/` → `raster-service` directly.

## Tests run

```text
pytest -q \
  tests_v9/test_raster_tilejson_cache_index_fix_20260626.py \
  tests_v9/test_raster_field_tenant_authz.py \
  tests_v9/test_raster_security_visual_fixes_20260626.py -q

30 passed
```

## Notes

Frontend package tests could not be executed in this container because `frontend/node_modules` is not present in the archive. Static regression checks were added for frontend changes.
