# Raster main.py Decomposition — Phase 17/18 Fields Router Finalization

Date: 2026-07-06
Base: `sahool_main_7b7f2b9_raster_main_decomposed_phase16.zip`
Output: `sahool_main_7b7f2b9_raster_main_decomposed_phase18.zip`

## Scope

This continuation completed the staged router decomposition after phase 16. The remaining router dependency was:

- `services/raster-service/routers/fields.py`

The goal was to remove the last `import main` / `main.*` dependency from routers while preserving legacy monkeypatch compatibility for existing tests and keeping `main.py` as a thin application/bootstrap facade.

## Changes

### Added

- `services/raster-service/raster_field_runtime.py`
  - Field-router runtime adapter exposing the helper/model/runtime names used by `routers/fields.py` without importing `main.py`.
  - Wraps extracted modules:
    - `raster_api_models.py`
    - `raster_runtime_state.py`
    - `raster_security_context.py`
    - `raster_settings.py`
    - `raster_date_geo.py`
    - `layer_lookup.py`
    - `stac_search.py`
    - `scene_policy.py`
    - `tile_cache_io.py`
    - `raster_processing_runtime.py`
    - `raster_cdse_processing.py`
    - `raster_backfill_scene_processing.py`
    - `raster_quality.py`
    - `tile_observability.py`

- `services/raster-service/test_router_no_main_import_static.py`
  - Static pytest guard preventing all raster routers from importing or using `main.*`.

### Modified

- `services/raster-service/routers/fields.py`
  - Removed `import main`.
  - Replaced `main.*` references with imports from `raster_field_runtime.py`.
  - Kept endpoint behavior unchanged.
  - Uses dynamic `_upload_dir()` where tests/runtime can override `main.UPLOAD_DIR` during staged compatibility.

- `scripts/ci/raster_main_decomposition_gate.py`
  - Added `raster_field_runtime.py` to required extracted modules.
  - Changed router dependency validation from a fixed allowlist to scanning every file under `services/raster-service/routers/*.py`.
  - Now fails if any router imports `main`, imports from `main`, or uses `main.*`.

- `services/raster-service/test_landsat_thermal_unique_contract.py`
  - Updated static checks to match the new router-direct-import architecture instead of requiring `main.*` strings.

- Router docstrings
  - Cleaned stale text claiming shared dependencies remain in `main.py`.

## Compatibility notes

Some existing tests monkeypatch `main.AGENT_TOKEN`, `main._stac_search`, `main._run_processing`, and `main._field_owner`. `raster_field_runtime.py` preserves this during the transition via dynamic lookup from `sys.modules['main']` without making routers import `main.py` directly.

## Result

- `main.py`: 608 lines, unchanged from phase 16.
- Routers importing/using `main`: 1 → 0.
- Required extracted modules in guard: 22.
- Raster tests: 156 passed.

## Verification executed

```bash
python3 -m compileall -q services/raster-service scripts/ci services/sahool-platform/api
python3 scripts/ci/raster_main_decomposition_gate.py
PYTHONPATH=services/raster-service python3 -m pytest -q services/raster-service
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

Observed:

- `raster-main-decomposition contract: OK (main.py lines=608, modules=22)`
- `156 passed`
- All listed gates passed.
- Compose YAML files validated.
- Router main dependency scan: OK.

## Remaining optional work

1. Remove compatibility lookups from `raster_field_runtime.py` after tests are migrated away from monkeypatching `main.*`.
2. Reduce `main.py` below 500 lines by moving remaining app bootstrap/middleware aliases into a service factory.
3. Add a full import smoke test for all extracted runtime modules under a production-like environment.
