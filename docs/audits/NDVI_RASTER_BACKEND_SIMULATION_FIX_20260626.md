# NDVI/Raster backend source review and simulation fix — 2026-06-26

## Scope
Reviewed and simulated the critical path:

Sentinel/CDSE → processing → COG → raster_assets rehydrate → tile endpoint → Leaflet/MapLibre.

Files checked:
- `services/raster-service/db_persist.py`
- `services/raster-service/main.py`
- `services/raster-service/tile_render.py`
- `frontend/src/components/maphub/HubMap.tsx`
- `frontend/src/components/maphub/HubMapGL.tsx`
- `frontend/src/sections/MapHub.tsx`

## Confirmed already fixed
- RLS uses `set_config('app.current_tenant', $1, false)` in raster asset insert/fetch/list.
- `HubMap.tsx` and `HubMapGL.tsx` pass `tenantId` and `imageryTs` into tile URLs.
- TileLayer/MapLibre URLs include `tid` and `v` cache-busting parameters.
- `TileLayer` key includes `imageryTs` to force Leaflet reload.
- Synthetic COG tile rendering produces non-transparent pixels above the field and transparent tiles outside.

## New source-level issue found
Tile image requests are not axios requests and therefore do not carry the normal `X-Tenant-Id` header. The frontend correctly appended `tid=...`, but raster-service middleware ignored query `tid` and only read `X-Tenant-Id`.

This caused DB rehydration after restart to call:

```python
fetch_latest_asset(..., tenant_id=None)
```

Because `fetch_latest_asset` is tenant-filtered and RLS-aware, this returns no COG and the tile endpoint returns the transparent PNG. The UI then shows field boundaries but no NDVI overlay.

## Fix
Updated `services/raster-service/main.py`:

- Added `_tenant_from_request(request)`.
- It prefers trusted `X-Tenant-Id`.
- It falls back to `tid`/`tenant_id` query parameters for TileLayer/MapLibre image requests.
- Existing field ownership guard still checks field owner when DB is available.
- `fetch_latest_asset` now receives the tenant hint and can rehydrate persisted COGs.

## Tests added
Added `services/raster-service/test_tile_tenant_query.py`:

- `test_tilejson_query_tid_rehydrates_db_with_tenant`
- `test_tile_query_tid_is_used_when_rendering_after_restart`

These prevent regression where `tid` is ignored and NDVI tiles silently become transparent after restart.

## Verification
- Raster-service full tests: `32/32 passed`
- `verify_review_fixes.py`: `23/23 passed`
- Python compile for raster-service files: passed
- Manual simulation: `/v1/fields/F-123/tilejson?...&tid=T-1` now calls `fetch_latest_asset(... tenant_id='T-1')`.

## Remaining live-environment checks
Run in the development environment:

```bash
curl -I 'http://localhost:8001/v1/fields/<FIELD_ID>/tilejson?index=ndvi&tid=<TENANT_ID>&v=1'
curl -s -o /tmp/tile.png 'http://localhost:8001/v1/fields/<FIELD_ID>/tiles/14/<x>/<y>.png?index=ndvi&tid=<TENANT_ID>&v=1'
ls -lh /tmp/tile.png
```

Expected tile size above the field should be materially larger than the 1x1 transparent PNG.
