# RASTER MAIN DECOMPOSITION — PHASE 5 ORCHESTRATION

Date: 2026-07-06

## Scope

Conservative continuation of the staged breakup of `services/raster-service/main.py`.
This phase extracts raster job orchestration while preserving compatibility wrappers
inside `main.py` so existing routers/tests can keep importing the old private names.

## New module

- `services/raster-service/raster_job_orchestration.py`

## Moved logic

- `_run_processing` → `raster_job_orchestration.run_processing(ctx, job_id, req)`
- `_run_batch_processing` → `raster_job_orchestration.run_batch_processing(ctx, job_id, req)`

`main.py` now keeps wrappers:

- `_run_processing(job_id, req)`
- `_run_batch_processing(job_id, req)`

The wrappers pass `sys.modules[__name__]` as a context object so runtime state remains
owned by `main.py` during the staged decomposition.

## Why context-based extraction

The processing flow still uses shared runtime state and helpers:

- `_jobs`
- `_layers`
- `_field_layers`
- `_process_precomputed_pixels`
- `_process_pixels`
- `_persist_raster_asset`
- `JobStatus`
- logger

Passing the module context avoids a risky big-bang dependency inversion while removing
the orchestration body from the large application module.

## Size impact

- `main.py` after phase 4: 2119 lines
- `main.py` after phase 5: 1919 lines

Net reduction: 200 lines.

## CI guard update

Updated:

- `scripts/ci/raster_main_decomposition_gate.py`

It now requires:

- `raster_job_orchestration.py`
- `run_processing`
- `run_batch_processing`
- compatibility wrapper calls in `main.py`
- `main.py` line count <= 1950

## Verification

Passed:

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

Raster targeted tests:

```text
33 passed, 1 warning
```

Tests:

- `test_raster_router_decomposition_guard.py`
- `test_historical_backfill.py`
- `test_landsat_thermal_unique_contract.py`
- `test_cdse_date_normalization.py`
- `test_tile_tenant_query.py`

## Remaining high-risk functions still in main.py

These remain intentionally for later phases:

- `_process_precomputed_pixels`
- `_process_precomputed_truecolor`
- `_process_pixels`
- `_run_cdse_processing`

Recommended next phase: extract pixel processing into `raster_pixel_processing.py` using
the same context-based compatibility pattern, then leave CDSE orchestration for the last
step.
