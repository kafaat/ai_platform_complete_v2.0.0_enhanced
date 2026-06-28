# SAHOOL Raster/Map Deep Scan — 2026-06-26

## Scope
Direct source review of the runtime path that can cause the map artifact/date mismatch:

`MapHub UI → platform /api/v1/fields/{id}/imagery/refresh and available-dates → raster-service CDSE Process/Catalog → raster_assets → TileJSON → /tiles`.

## Additional issues found and fixed

### 1. MapLibre date-change bug
`HubMapGL.tsx` rebuilt the indicator raster source when indicator/field/opacity/tenant/cache-bust changed, but not when `imageryDate` changed. In 3D/MapLibre mode, choosing another scene date could keep the previous tile source.

Fix: added `imageryDate` to the indicator synchronization dependency list.

### 2. Server-side tile cache ignored cache-bust version
The frontend appended `v=<imageryTs>` to tile URLs, but `/v1/fields/{field_id}/tiles/{z}/{x}/{y}.png` did not accept `v`, so the raster-service tile cache key ignored it. A new COG or date refresh could still serve stale PNG tiles.

Fix: added `v` Query parameter to `field_tile()` and included it in `_tile_cache_key(...)`.

### 3. Missing platform/raster available-dates runtime chain
The frontend called `/api/v1/fields/{fieldId}/available-dates`, but no real platform route existed in the source path. This made the scene selector silently empty, pushing the UI back to `latest`.

Fix:
- Added raster endpoint: `GET /v1/fields/{field_id}/available-dates`.
- Added platform proxy endpoint: `GET /api/v1/fields/{field_id}/available-dates`.
- Both are tenant-verified.
- Raster returns actual persisted/generated COG dates, not fabricated provider dates.

### 4. CDSE acquisition date mismatch
CDSE Process API was run over a lookback window and the persisted `capture_datetime` was set to `time_to` (usually “today”). If the provider chose a scene from another day, `raster_assets.acquisition_date` was wrong. This breaks date selection and can mix apparent scene dates.

Fix:
- CDSE processing now searches Catalog first, picks a real acquisition scene/date, narrows processing to that acquisition day, and persists the real capture datetime.
- Explicit date refresh is supported via `date_from/date_to`.

### 5. Manual refresh could not target selected date
The frontend date selector changed tile URLs, but manual refresh still posted no date to the platform. If a selected date was missing a COG, refresh could regenerate latest instead of the selected date.

Fix:
- `refreshFieldImagery(fieldId, date)` now sends `{date}` when a scene date is selected.
- Platform accepts `FieldImageryRefreshRequest.date`.
- Imagery automation passes that date to raster CDSE processing.

## Verification
- Python syntax compile passed for modified Python files.
- Static regression checks passed for:
  - MapLibre date dependency
  - tile cache version propagation
  - CDSE acquisition-date binding
  - raster available-dates endpoint
  - platform available-dates proxy
  - selected-date refresh propagation

Note: full `pytest tests_v9` is still blocked in this environment by missing `jose`, from the existing test conftest.
