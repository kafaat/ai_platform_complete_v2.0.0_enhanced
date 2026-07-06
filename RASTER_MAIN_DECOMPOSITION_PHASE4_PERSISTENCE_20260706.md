# RASTER_MAIN_DECOMPOSITION_PHASE4_PERSISTENCE_20260706

## Scope

Conservative phase 4 decomposition of `services/raster-service/main.py`.

This phase extracted raster asset persistence from the FastAPI application module while preserving all public/private compatibility names used by existing routers and tests.

## Added

- `services/raster-service/raster_asset_persistence.py`

The new module owns:

- `_is_valid_uuid_text`
- `_is_valid_field_id_text`
- `persist_raster_asset`
- compatibility alias `_persist_raster_asset`

## Main compatibility

`main.py` now imports and re-exports:

```python
from raster_asset_persistence import (
    _is_valid_field_id_text,
    _is_valid_uuid_text,
    persist_raster_asset as _persist_raster_asset,
)
```

This keeps old tests and routers working while removing the DB persistence implementation from `main.py`.

## Size reduction

- Before phase 4: 2307 lines
- After phase 4: 2119 lines

## CI guard update

Updated:

- `scripts/ci/raster_main_decomposition_gate.py`

The gate now requires `raster_asset_persistence.py`, checks its exports, prevents the persistence/validation functions from returning to `main.py`, and caps `main.py` at 2150 lines.

## Verification

Executed successfully:

```bash
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
pytest -q services/raster-service/test_raster_assets_text_field_id.py \
  services/raster-service/test_raster_router_decomposition_guard.py \
  services/raster-service/test_historical_backfill.py \
  services/raster-service/test_landsat_thermal_unique_contract.py \
  services/raster-service/test_cdse_date_normalization.py \
  services/raster-service/test_tile_tenant_query.py
```

Result:

- `36 passed`
- all contract gates passed

## Not moved yet

Still intentionally left in `main.py`:

- `_run_processing`
- `_run_batch_processing`
- `_process_precomputed_pixels`
- `_process_precomputed_truecolor`
- `_process_pixels`
- `_run_cdse_processing`

These are the job orchestration and pixel-processing paths and should be extracted in a separate phase using an explicit processing context rather than direct large-scale movement.
