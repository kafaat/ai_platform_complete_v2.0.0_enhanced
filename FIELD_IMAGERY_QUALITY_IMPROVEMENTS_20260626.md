# SAHOOL — Field imagery quality improvements (2026-06-26)

## Scope
Applied the requested best-practice improvements for field imagery, aerial/satellite index tiles, and FieldIndicatorMap verification.

## Implemented

1. **Pixel API quality/confidence**
   - `GET /v1/fields/{field_id}/pixel?lat=&lon=&index=&date=` now returns:
     - `confidence`
     - `quality`
     - `quality_reason`
     - `cloud_pct`
   - Valid pixels use the field-AOI SCL cloud percentage when available.
   - Masked/nodata pixels return `confidence=0.0` and `quality=nodata`.

2. **Field-AOI cloud percentage and layer quality**
   - `_process_pixels()` already computes `cloud_pct` from SCL over the clipped field AOI.
   - Added `_quality_from_cloud_pct()` to convert AOI cloud percentage into a conservative 0..1 confidence score.
   - Stored `confidence`, `quality`, and `quality_reason` in processing `stats`.
   - Attached cloud/quality metadata to in-memory layer records for tiles/grid/pixel endpoints.

3. **Persistence/rehydration of cloud quality metadata**
   - `raster_assets` persistence now records the quality metadata inside `provenance.stats`.
   - `db_persist.fetch_latest_asset()` rehydrates:
     - `cloud_pct`
     - `confidence`
     - `quality`
     - `cloud_mask_applied`
   - This prevents quality metadata loss after service restart.

4. **Indicator grid metadata**
   - `GET /v1/fields/{field_id}/indicator-grid` now exposes layer-level:
     - `cloud_pct`
     - `confidence`
     - `quality`
   - This helps the UI distinguish reliable imagery from questionable imagery.

5. **FieldIndicatorMap regression tests**
   - Added `frontend/src/components/FieldIndicatorMap.static.test.ts` covering:
     - `tid` propagation in TileJSON and tile URLs.
     - No fake indicator layer when TileJSON fails or `available=false`.
     - Field boundary remains visible independently from imagery availability.

## Tests run

Backend targeted tests:

```bash
PYTHONPATH=services/raster-service pytest -q \
  tests_v9/test_raster_security_visual_fixes_20260626.py \
  services/raster-service/test_clip_grid.py \
  services/raster-service/test_tiles.py \
  services/raster-service/test_tile_tenant_query.py
```

Result: **19 passed**

Frontend targeted test:

```bash
cd frontend && npm run test -- --run src/components/FieldIndicatorMap.static.test.ts
```

Result: **3 passed**

## Notes
- Full visual confirmation still requires running the platform in a browser with live raster assets and fields.
- The implementation does not invent quality values when SCL/cloud metadata is unavailable; it returns conservative `quality=unknown` with `confidence=0.55`.
