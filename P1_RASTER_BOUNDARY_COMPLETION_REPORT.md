# P1 Raster Boundary Completion Report

## Scope

Implemented the first post-P0 service-boundary hardening layer for Raster/Imagery ownership.
This PR does not attempt a risky extraction. It locks the current seam and prevents new raster domain logic from growing inside `sahool-platform`.

## Added files

- `docs/architecture/RASTER_BOUNDARY_CONTRACT.md`
- `docs/architecture/raster_boundary_allowlist.json`
- `services/sahool-platform/tests/test_p1_raster_boundary_guard.py`

## Guards added

1. Raster-like platform routes must either target `raster-service` in `platform_extraction_map.json` or be an explicit legacy compatibility exception.
2. Any platform source file containing raster concepts must be listed in `raster_boundary_allowlist.json`.
3. `sahool-platform` must not import internal modules from `services/raster-service`; it must use HTTP/contracts.
4. Raster-owned tables must have exactly one writer: `raster-service`.

## Result

The current codebase passes the P0 + P1 boundary guards. The boundary is now enforceable before deeper extraction.

Verified command:

```bash
pytest -q \
  services/sahool-platform/tests/test_p0_platform_route_ownership_guard.py \
  services/sahool-platform/tests/test_p0_db_ownership_guard.py \
  services/sahool-platform/tests/test_p0_platform_module_growth_guard.py \
  services/sahool-platform/tests/test_p1_raster_boundary_guard.py
```

Result: `10 passed`.

During implementation the guard exposed one important ownership correction: `zonal_stats` was still listed as `sahool-platform` owned. It is now classified as `raster-service` owned with `sahool-platform` as reader.

## Next extraction candidates

1. Retire legacy `/api/vegetation/*` compatibility paths after gateway validation.
2. Move `api/routers/gis_cloud_native.py` STAC/COG compatibility routes behind raster-service/gateway.
3. Replace direct platform reads of raster-owned tables with raster-service summary endpoints where performance allows.
4. Keep field geometry invalidation in platform, but ensure recomputation remains in raster-service/worker.
