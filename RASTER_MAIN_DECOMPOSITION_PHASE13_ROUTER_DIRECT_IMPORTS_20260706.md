# RASTER main.py decomposition — Phase 13: router direct imports

## Scope

This phase did not attempt to shrink `services/raster-service/main.py` further. After phase 12 it is already a small compatibility facade (608 lines). The next safer architectural step was to reduce router coupling to `main.*` by moving selected routers to direct imports from the extracted modules.

## Changed routers

The following routers no longer import `main` and no longer call `main.*`:

- `services/raster-service/routers/jobs.py`
- `services/raster-service/routers/imagery_search.py`
- `services/raster-service/routers/timeseries_routes.py`
- `services/raster-service/routers/storage.py`

## Direct module dependencies introduced

- `raster_api_models.py`
- `raster_runtime_state.py`
- `raster_security_context.py`
- `raster_settings.py`
- `stac_search.py`

## Why these routers first

These routers were selected because their dependencies are already well-isolated after phases 1–12:

- `jobs.py` only needs job runtime state, auth, and `JobStatus`.
- `imagery_search.py` only needs STAC helpers, `SearchRequest`, and service-token auth.
- `timeseries_routes.py` only needs STAC search, `TimeSeriesAnalyzeRequest`, and service-token auth.
- `storage.py` only needs upload/offline-pack settings, logging, and service-token auth.

More complex routers such as `fields.py`, `cdse_tiles.py`, and `tiles.py` still touch multiple compatibility wrappers and should be migrated in smaller batches.

## Guard updates

Updated:

- `scripts/ci/raster_main_decomposition_gate.py`

The gate now prevents the four migrated routers from regressing back to `import main`, `from main`, or `main.*` attribute access.

## Verification

Executed successfully:

```text
python3 -m compileall -q services/raster-service scripts/ci services/sahool-platform/api
PYTHONPATH=services/raster-service:services/sahool-platform:. pytest -q services/raster-service
```

Result:

```text
155 passed
```

Executed CI contract gates successfully:

```text
raster-main-decomposition contract: OK (main.py lines=608, modules=19)
MinIO/S3 contract: OK
compose-env contract: OK
backfill-ui-sync contract: OK
runtime-readiness contract: OK
mobile contract: OK
public-weather-route-governance contract: OK
service-port-gate: PASS
nginx-compose-dns-gate: PASS (15 upstreams)
v9-gpu-contract-gate: PASS
runtime-contract-gate: PASS
```

## Remaining optional migration

Routers still importing `main`:

- `analysis.py`
- `cdse_tiles.py`
- `fields.py`
- `imagery.py`
- `observability.py`
- `processing.py`
- `soil_tiles.py`
- `terrain_tiles.py`
- `tiles.py`

Recommended next phase: migrate `processing.py` after introducing a narrow processing context module, or migrate `imagery.py` because it has a small dependency surface.
