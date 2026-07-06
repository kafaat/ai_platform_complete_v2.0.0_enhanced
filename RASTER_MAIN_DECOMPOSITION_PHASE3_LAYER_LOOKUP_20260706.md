# RASTER MAIN DECOMPOSITION — PHASE 3 LAYER LOOKUP

Date: 2026-07-06
Scope: `services/raster-service/main.py`

## Summary

Phase 3 continued the conservative decomposition of `raster-service/main.py` by extracting field-layer lookup, COG grid rendering helpers, DB rehydration, and SAR/RVI field helpers into a dedicated module while preserving all public `main._*` compatibility symbols used by existing routers/tests.

## Added module

```text
services/raster-service/layer_lookup.py
```

Moved logic:

```text
GRID_INDEX_ALIASES
normalize_index
display_index
find_field_layer
grid_from_cog
rehydrate_field_layer_from_db
resolve_field_layer
rvi_from_sar_cog
real_field_grid
```

## Compatibility kept in main.py

`main.py` now contains thin wrappers:

```text
_normalize_index
_display_index
_find_field_layer
_grid_from_cog
_rehydrate_field_layer_from_db
_resolve_field_layer
_rvi_from_sar_cog
_real_field_grid
```

Routers still call `main._resolve_field_layer`, `main._grid_from_cog`, etc. No public route contract changed.

## Size reduction

```text
main.py after phase 2: 2471 lines
main.py after phase 3: 2307 lines
additional reduction: 164 lines
```

## CI guard update

Updated:

```text
scripts/ci/raster_main_decomposition_gate.py
```

The guard now requires `layer_lookup.py`, verifies expected exports, verifies wrappers in `main.py`, and lowers the `main.py` line limit to 2350.

## Verification performed

```text
python -m compileall -q services/raster-service scripts/ci services/sahool-platform/api
python scripts/ci/raster_main_decomposition_gate.py
python scripts/ci/minio_s3_contract_gate.py
python scripts/ci/compose_env_contract_gate.py
python scripts/ci/backfill_ui_sync_gate.py
python scripts/ci/runtime_readiness_contract_gate.py
python scripts/ci/mobile_contract_gate.py
python scripts/ci/public_weather_route_governance_gate.py
python scripts/ci/service_port_gate.py
python scripts/ci/nginx_compose_dns_gate.py
python scripts/ci/v9_gpu_contract_gate.py
python scripts/ci/runtime_contract_gate.py
```

Selected raster tests:

```text
36 passed
```

Files tested:

```text
services/raster-service/test_raster_router_decomposition_guard.py
services/raster-service/test_historical_backfill.py
services/raster-service/test_landsat_thermal_unique_contract.py
services/raster-service/test_cdse_date_normalization.py
services/raster-service/test_tile_tenant_query.py
services/raster-service/test_db_rehydrate.py
services/raster-service/test_tenant_propagation.py
```

YAML validation passed for:

```text
docker-compose.v9.yml
docker-compose.fixed.yml
docker-compose.v9.gpu.yml
.github/workflows/ci.yml
```

## Deliberately not moved yet

Still left in `main.py` because they are high-risk orchestration functions touching job state, DB persistence, COG writing, and in-memory layer maps:

```text
_persist_raster_asset
_run_processing
_run_batch_processing
_process_precomputed_pixels
_process_precomputed_truecolor
_process_pixels
_run_cdse_processing
```

Recommended next phase: extract only `_persist_raster_asset` first into a `raster_asset_persistence.py` adapter with explicit injected dependencies, before touching processing/job orchestration.
