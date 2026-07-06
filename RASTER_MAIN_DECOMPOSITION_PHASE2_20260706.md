# Raster main.py decomposition — Phase 2

## Scope

Continued the conservative breakup of `services/raster-service/main.py` after the first phase. This phase extracted the STAC/catalogue search surface while preserving all public helper names that routers, workers, and tests still import through `main`.

## New module

Added:

```text
services/raster-service/stac_search.py
```

The module owns:

```text
band_urls_from_assets
stac_query
stac_search
stac_search_cdse
stac_search_element84
stac_search_radar
landsat_thermal_href
landsat_unique_payload
stac_search_landsat
stac_search_landsat_unique
stac_search_dem
```

## Compatibility retained

`main.py` still re-exports the historical underscored helper names:

```text
_band_urls_from_assets
_stac_query
_stac_search
_stac_search_cdse
_stac_search_element84
_stac_search_radar
_landsat_thermal_href
_landsat_unique_payload
_stac_search_landsat
_stac_search_landsat_unique
_stac_search_dem
```

This keeps existing imports in routers/workers/tests working, including monkeypatch-based tests.

## Size impact

```text
main.py before phase 2: 2803 lines
main.py after phase 2: 2471 lines
```

## CI hardening

Updated:

```text
scripts/ci/raster_main_decomposition_gate.py
```

The gate now requires `stac_search.py`, forbids STAC search helper definitions from returning to `main.py`, checks compatibility aliases, and lowers the maximum allowed `main.py` size to 2550 lines.

## Verification run

Executed successfully:

```text
python3 -m compileall -q services/raster-service scripts/ci services/sahool-platform/api
python3 scripts/ci/raster_main_decomposition_gate.py
python3 scripts/ci/minio_s3_contract_gate.py
python3 scripts/ci/compose_env_contract_gate.py
python3 scripts/ci/backfill_ui_sync_gate.py
python3 scripts/ci/runtime_readiness_contract_gate.py
python3 scripts/ci/mobile_contract_gate.py
python3 scripts/ci/public_weather_route_governance_gate.py
python3 scripts/ci/service_port_gate.py
python3 scripts/ci/nginx_compose_dns_gate.py
python3 scripts/ci/v9_gpu_contract_gate.py
python3 scripts/ci/runtime_contract_gate.py
```

Selected raster tests:

```text
33 passed
```

Files:

```text
test_raster_router_decomposition_guard.py
test_historical_backfill.py
test_landsat_thermal_unique_contract.py
test_cdse_date_normalization.py
test_tile_tenant_query.py
```

## Not changed intentionally

The processing/job orchestration functions are still in `main.py`:

```text
_run_processing
_run_batch_processing
_process_precomputed_pixels
_process_precomputed_truecolor
_process_pixels
_run_cdse_processing
```

They are more stateful and touch jobs, layer maps, persistence, COG writing, and CDSE processing. They should be moved in a later phase with a dedicated processing context object, not by a blind copy.
