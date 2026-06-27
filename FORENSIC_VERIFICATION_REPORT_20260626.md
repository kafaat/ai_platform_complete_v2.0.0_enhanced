# SAHOOL Raster/Map Forensic Verification — 2026-06-26

## Scope
Direct source-code verification for the remaining map/raster suspected causes:
- MapLibre stale raster source reuse
- `latest` hard-coded tile date
- CDSE bbox/CRS validation
- tile cache key drift
- COG mask/nodata hardening

## Verified Results

### Closed
- `HubMapGL.tsx` no longer calls `.setTiles(` in runtime code.
- MapLibre basemap updates now remove/recreate raster source instead of mutating tiles in-place.
- `HubMap.tsx` and `HubMapGL.tsx` build tile URLs with `imageryDate || 'latest'`, not hard-coded `date=latest`.
- Raster tile cache key includes tenant, field, index, date, version, z, x, y.
- CDSE client validates bbox as EPSG:4326 and sends CRS `http://www.opengis.net/def/crs/EPSG/0/4326`.
- COG writer writes an internal mask with `dst.write_mask(...)` and uses explicit nodata.

### Test/Verification Commands
- `python3 -m py_compile services/raster-service/main.py services/raster-service/cdse_client.py services/raster-service/cog_writer.py services/raster-service/tile_render.py`
- `python3 -m pytest -q services/raster-service/test_raster_map_deep_hardening_static.py services/raster-service/test_tiles.py`
- custom static assertions over HubMapGL, HubMap, raster main, cdse_client, cog_writer

### Results
- Python compile: PASS
- Raster targeted tests: 7 passed
- Static forensic assertions: PASS

### Not Run
- Frontend Vitest could not run because `vitest` is not installed in this environment.
