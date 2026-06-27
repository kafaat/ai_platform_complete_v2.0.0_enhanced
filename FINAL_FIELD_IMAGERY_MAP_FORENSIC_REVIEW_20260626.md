# FINAL FIELD / IMAGERY / MAP FORENSIC REVIEW — 2026-06-26

## Scope
Reviewed the runtime chain for fields, imagery, indices, synchronization, APIs, tiles, clipping/masking, TIF/PNG handling, legacy routes, drawing tools, automatic area calculation, field persistence, migrations, temporary/permanent cache, queries, imports, requests, and events.

## Fixes applied in this final pass

1. **FieldIndicatorMap cache-version wiring**
   - `TileJSON.cache_version` / `resolved_date` is now consumed by `FieldIndicatorMap`.
   - Returned indicator PNG tile URLs now include `v=<cache_version>` so refreshed COGs do not keep stale browser/CDN tile images.
   - The Leaflet TileLayer key now includes field + index + date + cache version.

2. **ScoutingMap tenant-safe tile requests**
   - Removed its local raster tile URL builder.
   - Rewired it to the canonical `fieldIndicatorTileUrl()` helper.
   - Propagates `tid` using `getTenantId()` because tile images are `<img>` requests and do not carry Axios headers.
   - Removed a duplicate unreachable `return` in the old local URL builder.

3. **FieldMapCenter date synchronization**
   - No longer forces map panels to `date="latest"` when real imagery dates exist.
   - Fetches `available-dates` for the active field and exposes an imagery date selector.
   - Passes the selected date to single-layer and side-by-side map panels.
   - Removed duplicate `setFieldId()` call and duplicate compare-mode icon.

4. **Migration manifest completeness**
   - Added `v107_phase9_10_event_drift_hardening.sql` to `migrations/MANIFEST.txt`.
   - This prevents event/drift hardening tables from being skipped during official migration application.

5. **Regression tests added**
   - Added `services/raster-service/test_final_field_imagery_runtime_contract_static_20260626.py`.
   - It guards against stale tile cache keys, missing tenant propagation, forced `latest`, missing v107 manifest entry, and known raster/map red flags.

## Checks executed

- Python syntax validation:
  - `1322` Python files compiled successfully.
  - `0` syntax errors.

- Targeted raster/map tests:
  - `18 passed`
  - Included:
    - final static field/imagery runtime contract checks
    - raster tiles
    - tenant query / TileJSON propagation
    - raster map deep hardening static checks

- Runtime red-flag scan, excluding tests:
  - `setTiles(`: `0`
  - `nodata=None`: `0`
  - `method="first"`: `0`
  - `method='first'`: `0`
  - `geometry.bounds`: `0`

- Migration validator:
  - All manifest entries exist on disk.
  - Known validator warning remains in `v18_entity_ids_text.sql` about `ON CONFLICT (dedup_key)`, but `v11_events_bus.sql` defines the required partial unique index. This is a validator limitation/manual-review item, not a new breakage.

## Remaining limits

Full runtime confidence still requires an environment with:
- PostgreSQL/PostGIS
- Redis
- NATS
- running raster-service container
- frontend `node_modules`
- CDSE credentials/network access

`tests_v9` could not run here because `jose` is missing in this environment. Frontend typecheck/Vitest could not run because `node_modules` are not installed.

## Final assessment

The code path is now substantially hardened for:
- field imagery date synchronization
- COG/tile refresh consistency
- tenant-safe tile image requests
- TileJSON-to-tile cache version propagation
- map runtime stale-tile prevention
- official migration manifest completeness

Production validation should next run Docker E2E against the live stack.
