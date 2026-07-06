# Raster main.py decomposition — Phase 15

Date: 2026-07-06

## Scope

Phase 15 continued the post-main decomposition by reducing router dependencies on `main.*`.

Converted these routers to direct imports from extracted modules:

- `services/raster-service/routers/observability.py`
- `services/raster-service/routers/analysis.py`
- `services/raster-service/routers/soil_tiles.py`
- `services/raster-service/routers/terrain_tiles.py`

## New/updated module exports

Updated:

- `services/raster-service/stac_search.py`

Added helper:

- `stac_health()`

This allows the observability router to read STAC health counters without importing `main._stac`.

## Router dependency changes

Routers now import directly from:

- `raster_api_models.py`
- `raster_runtime_state.py`
- `raster_security_context.py`
- `raster_settings.py`
- `raster_quality.py`
- `tile_observability.py`
- `layer_lookup.py`
- `stac_search.py`

## Result

Routers still importing `main`:

Before phase 15: 7

After phase 15: 3

Remaining:

- `routers/cdse_tiles.py`
- `routers/fields.py`
- `routers/tiles.py`

`main.py` stayed at 608 lines. This phase focused on dependency direction, not line-count reduction.

## Contract guard

Updated:

- `scripts/ci/raster_main_decomposition_gate.py`

It now prevents the converted routers from importing `main` or using `main.*`, and verifies `stac_search.stac_health` exists.

## Verification

Executed successfully:

```bash
python3 -m compileall -q services/raster-service scripts/ci services/sahool-platform/api
PYTHONPATH=services/raster-service python3 -m pytest -q services/raster-service
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

Result:

- `155 passed`
- `raster-main-decomposition contract: OK (main.py lines=608, modules=20)`
- all listed CI contract gates passed
- compose/workflow YAML parsed successfully

## Remaining recommended next step

Convert `routers/tiles.py` next, then `routers/cdse_tiles.py`, and keep `routers/fields.py` last because it is the heaviest and most coupled router.
