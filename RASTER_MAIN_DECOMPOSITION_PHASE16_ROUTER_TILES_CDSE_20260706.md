# RASTER MAIN DECOMPOSITION — PHASE 16 ROUTER TILES/CDSE

Date: 2026-07-06

## Scope

Continued the post-main decomposition by removing direct `main` coupling from the remaining tile routers before touching the large `fields.py` router.

## Changed files

- `services/raster-service/routers/tiles.py`
  - Removed `import main`.
  - Uses direct imports from:
    - `raster_runtime_state`
    - `raster_security_context`
    - `raster_settings`

- `services/raster-service/routers/cdse_tiles.py`
  - Removed `import main`.
  - Delegates CDSE tile normalization/cache/COG guarantee to a dedicated module.

- `services/raster-service/raster_cdse_tile_runtime.py`
  - New extracted module for CDSE live tile runtime helpers:
    - `parse_poly`
    - `normalize_cdse_request`
    - `ensure_field_cog`
    - `tilejson_availability`

- `services/raster-service/test_cdse_poly_contract.py`
  - Updated static contract to read both the router and the extracted runtime module, preserving the same guard after decomposition.

- `scripts/ci/raster_main_decomposition_gate.py`
  - Added `raster_cdse_tile_runtime.py` to required extracted modules.
  - Added `routers/tiles.py` and `routers/cdse_tiles.py` to the direct-router-import guard.

## Result

Routers still importing `main` dropped from:

```text
3 -> 1
```

Remaining router:

```text
services/raster-service/routers/fields.py
```

`main.py` remains:

```text
608 lines
```

This phase intentionally targeted router coupling, not main.py line count.

## Verification

Executed:

```text
python -m compileall -q services/raster-service scripts/ci services/sahool-platform/api
python -m pytest -q services/raster-service
```

Result:

```text
155 passed
```

CI/static gates executed:

```text
raster-main-decomposition contract: OK (main.py lines=608, modules=21)
MinIO/S3 contract: OK
compose-env contract: OK
backfill-ui-sync contract: OK
runtime-readiness contract: OK
mobile contract: OK
public-weather-route-governance contract: OK
service-port-gate: PASS
nginx-compose-dns-gate: PASS
v9-gpu-contract-gate: PASS
runtime-contract-gate: PASS
YAML OK
```

## Remaining

Only `routers/fields.py` still imports `main`. It is the largest/highest-risk router and should be split last by feature group rather than converted in one large risky pass.
