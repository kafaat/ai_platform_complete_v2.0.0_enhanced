# SAHOOL Raster/Map Deep Hardening Fix — 2026-06-26

## Scope
Deep scan and hardening for potential causes of the map/tile striping and stale imagery problems across:

- `services/raster-service/cdse_client.py`
- `services/raster-service/main.py`
- `services/raster-service/cog_writer.py`
- `services/raster-service/tile_render.py`
- raster tile regression tests

## Confirmed additional risks found and fixed

### 1. Explicit CDSE date could become a zero-length time range
When UI selected a single date, `date_from` and `date_to` could both normalize to `YYYY-MM-DDT00:00:00Z`. This can lead to CDSE 400/empty processing or stale fallback behavior.

**Fix**
Bare dates now expand to a full day:

- `YYYY-MM-DDT00:00:00Z`
- `YYYY-MM-DDT23:59:59Z`

The persisted capture datetime is anchored to midday of the selected acquisition day.

### 2. CDSE bbox/geometry validation was not centralized
Invalid axis order, non-WGS84 bbox, or malformed geometry could reach CDSE and produce provider-side 400s.

**Fix**
Added strict validation/helpers:

- `_validate_bbox_4326()`
- `_geometry_object()`

Both Process API and Catalog Search now use these before sending requests.

### 3. Generated COGs relied on NaN nodata semantics only
NaN nodata can be inconsistent across GDAL, overviews, masks, and tile rendering. This may create edge artifacts or incorrect interpretation of outside-field pixels.

**Fix**
COG writer now:

- uses finite nodata metadata: `-9999.0`
- preserves NaN values for compatibility
- writes an internal GDAL mask from `np.isfinite(array)`

This keeps existing analytics behavior while improving rendering/overview safety.

### 4. TileJSON lacked resolved runtime metadata
The frontend could request `latest` while the backend resolved a specific COG. Without returning that resolved date/version, debugging and cache invalidation remain ambiguous.

**Fix**
TileJSON now returns:

- `resolved_date`
- `cache_version`

Tile URLs include the runtime version, so browser/cache mixing across COG updates is less likely.

### 5. Transparent fallback tiles could be cached as valid-looking empty data
Transparent fallback responses previously allowed short caching. During tile generation/failure, this can make missing tiles persist visually.

**Fix**
Transparent fallback tiles now use:

- `Cache-Control: no-store, max-age=0`
- `X-Sahool-Tile-Cache: transparent`
- `X-Sahool-Tile-Date`

## Verification

Executed:

```bash
python3 -m py_compile main.py cdse_client.py cog_writer.py tile_render.py
pytest -q test_raster_map_deep_hardening_static.py test_tiles.py test_clip_grid.py
```

Result:

```text
8 passed
```

## Remaining runtime checks on the live container
After deploying this ZIP, run:

```bash
docker compose build sahool-raster-service
docker compose up -d sahool-raster-service
docker logs sahool-raster-service --tail=200
```

Then inspect one TileJSON request:

```bash
curl -H "X-Tenant-Id: <tenant>" \
  "http://localhost:8001/v1/fields/<field_id>/tilejson?index=ndsi&date=2026-06-25"
```

Confirm response contains:

- `available: true`
- `resolved_date`
- `cache_version`
- tile URL includes `date=...` and `v=...`

If vertical seams still appear while indicator tiles are correct/transparent, the remaining issue is the Esri World Imagery basemap itself, not SAHOOL raster tiles.
