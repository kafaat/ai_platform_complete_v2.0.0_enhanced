# Raster Service `main.py` Decomposition Fix — 2026-07-06

## Scope

Applied a conservative decomposition to `services/raster-service/main.py` without changing public route contracts or the legacy `main.*` import surface used by routers/tests/workers.

## Extracted modules

- `services/raster-service/scene_policy.py`
  - scene datetime normalization
  - scene cloud/clear percentage helpers
  - quality labels and scores
  - scene ranking
  - historical backfill scene selection policy

- `services/raster-service/raster_date_geo.py`
  - `YYYY-MM-DD` parsing
  - historical backfill date-window calculation
  - GeoJSON bbox extraction
  - monthly search windows
  - field geometry bbox extraction

- `services/raster-service/tile_cache_io.py`
  - tile cache key construction
  - safe tile cache read/write IO

- `services/raster-service/cdse_singleflight.py`
  - CDSE tile cache state
  - global cache lock
  - per-key single-flight locks
  - stale lock pruning

## Compatibility strategy

`main.py` now re-exports the extracted helpers under their old private names, for example:

- `main._rank_scenes`
- `main._select_backfill_scenes_by_policy`
- `main._bbox_from_geojson`
- `main._month_windows`
- `main._cdse_key_lock`

This keeps existing routers and tests that import `main` working while reducing the physical size and responsibility of `main.py`.

## CI guard added

Added:

```text
scripts/ci/raster_main_decomposition_gate.py
```

and wired it into:

```text
.github/workflows/ci.yml
```

The gate verifies:

- extracted modules exist;
- expected functions remain in the extracted modules;
- `main.py` stays below the current line-count ceiling;
- critical helpers do not regress back into `main.py`;
- compatibility aliases remain available for current routers/workers/tests.

## Verification executed

Passed:

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
python services/raster-service/test_raster_router_decomposition_guard.py
python services/raster-service/test_historical_backfill.py
python services/raster-service/test_landsat_thermal_unique_contract.py
python services/raster-service/test_cdse_date_normalization.py
python services/raster-service/test_tile_tenant_query.py
```

Also verified YAML parsing for:

- `docker-compose.v9.yml`
- `docker-compose.fixed.yml`
- `docker-compose.v9.gpu.yml`
- `.github/workflows/ci.yml`

## Main size result

`services/raster-service/main.py` reduced from about `3140` lines to `2803` lines, while preserving route registration and legacy helper access.

## Runtime note

Docker daemon is not available in this execution environment, so final runtime validation should still be executed locally with:

```powershell
docker compose -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml --profile gpu config
docker compose -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml --profile gpu build --no-cache
docker compose -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml --profile gpu up -d
```
