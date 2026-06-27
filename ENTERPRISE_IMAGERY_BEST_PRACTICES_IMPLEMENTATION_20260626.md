# SAHOOL Enterprise Imagery Best Practices Implementation — 2026-06-26

## Implemented

1. **SCL + CLM/CLP cloud quality**
   - `BandMapping` now supports `scl`, `clm`, and `clp`.
   - `_process_pixels()` combines SCL cloud classes with s2cloudless-style CLM/CLP when available.
   - `cloud_pct`, `cloud_mask_sources`, `confidence`, and `quality` are stored in processing stats/provenance.

2. **Scene Ranking Engine**
   - New model: `SceneCandidate`.
   - New API: `POST /v1/imagery/scenes/rank`.
   - Ranking weights: cloud 50%, recency 20%, coverage 20%, provider quality 10%.
   - AOI cloud percentage overrides scene-level cloud cover.

3. **Mosaic Planning**
   - New API: `POST /v1/imagery/mosaic/plan`.
   - Uses STAC search + ranking to select least-cloud/most useful scenes.
   - Returns an honest plan instead of pretending to render a mosaic when sources are unavailable.

4. **Persistent Tile Cache**
   - Field XYZ tile rendering now uses tenant-scoped disk cache under `UPLOAD_DIR/tile_cache`.
   - Adds `X-Sahool-Tile-Cache: hit|miss`.
   - New API: `GET /v1/tile-cache/stats`.

5. **Geometry Versioning**
   - New migration: `migrations/v105_enterprise_imagery_best_practices.sql`.
   - New table: `field_geometry_versions` with PostGIS geometry, validity dates, RLS/FORCE RLS, GiST index.
   - New API: `POST /v1/fields/{field_id}/geometry/versions`.

6. **GeoParquet Analytics Export**
   - New API: `POST /v1/fields/analytics/geoparquet/export`.
   - Writes real GeoParquet when optional production deps are installed.
   - Falls back to explicit NDJSON without falsely labeling it GeoParquet.

7. **Historical Backfill Improvement**
   - Existing backfill now selects scenes using the Scene Ranking Engine instead of sorting only by scene cloud percentage.

8. **Policy API**
   - New API: `GET /v1/imagery/quality/policy`.
   - Exposes cloud mask, ranking, mosaic, tile cache, geometry history, and export policy to the frontend/admin UI.

## Verification

Targeted tests passed:

```text
17 passed
```

Covered files/tests:

- `test_enterprise_imagery_best_practices.py`
- `test_historical_backfill.py`
- `test_tile_tenant_query.py`
- `test_tiles.py`

## Main Files Changed

- `services/raster-service/main.py`
- `services/raster-service/db_persist.py`
- `services/raster-service/requirements.txt`
- `services/raster-service/test_enterprise_imagery_best_practices.py`
- `migrations/v105_enterprise_imagery_best_practices.sql`
- `migrations/MANIFEST.txt`

