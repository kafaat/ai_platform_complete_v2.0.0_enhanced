# Raster main.py decomposition — Phase 14

## Scope

Phase 14 continues the post-main decomposition by removing direct `main` imports from two additional raster routers:

- `services/raster-service/routers/imagery.py`
- `services/raster-service/routers/processing.py`

This phase focuses on router dependency direction rather than shrinking `main.py` further.

## Changes

### New module

Added:

```text
services/raster-service/raster_processing_runtime.py
```

This module provides a small runtime adapter that assembles the context required by the previously extracted `raster_job_orchestration.py` without requiring routers to import `main.py`.

Exports:

```text
make_processing_context
run_processing
run_batch_processing
```

### Router direct imports

`routers/imagery.py` now imports directly from:

```text
raster_api_models.py
scene_policy.py
stac_search.py
```

`routers/processing.py` now imports directly from:

```text
raster_api_models.py
raster_processing_runtime.py
raster_runtime_state.py
raster_security_context.py
```

Instead of:

```text
import main
main.*
```

### Guard update

Updated:

```text
scripts/ci/raster_main_decomposition_gate.py
```

The decomposition guard now requires:

```text
raster_processing_runtime.py
make_processing_context
run_processing
run_batch_processing
```

And prevents these routers from regressing to direct `main` imports:

```text
routers/jobs.py
routers/imagery.py
routers/imagery_search.py
routers/processing.py
routers/timeseries_routes.py
routers/storage.py
```

## Results

Direct router imports from `main` were reduced from:

```text
9 -> 7 routers
```

Remaining routers still depending on `main`:

```text
analysis.py
cdse_tiles.py
fields.py
observability.py
soil_tiles.py
terrain_tiles.py
tiles.py
```

`main.py` remains:

```text
608 lines
```

## Validation

Executed successfully:

```text
python3 -m compileall -q services/raster-service scripts/ci services/sahool-platform/api
python3 -m pytest -q services/raster-service
```

Result:

```text
155 passed
```

CI gates executed successfully:

```text
raster-main-decomposition contract: OK (main.py lines=608, modules=20)
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

## Recommended next phase

Continue with lower-risk routers before touching `fields.py`:

1. `observability.py`
2. `tiles.py`
3. `soil_tiles.py` / `terrain_tiles.py`
4. `cdse_tiles.py`
5. `analysis.py`
6. `fields.py` last
