# P2 Raster Facade Cleanup Report

## Scope

Built on the full P0–P1.4 package. This phase converts the first cleaned raster-facing platform routes from open-coded raster HTTP calls into a single platform facade client, while preserving platform RBAC/tenant verification and raster-service ownership of raster computation/state.

## Added

- `services/sahool-platform/api/raster_service_client.py`
- `docs/architecture/RASTER_FACADE_CLEANUP_CONTRACT.md`
- `services/sahool-platform/tests/test_p2_raster_facade_cleanup_guard.py`
- `P2_RASTER_FACADE_CLEANUP_REPORT.md`

## Modified

- `services/sahool-platform/api/routers/fields.py`
- `services/sahool-platform/api/routers/etc_dual.py`
- `docs/architecture/raster_boundary_allowlist.json`
- `docs/architecture/platform_python_module_baseline.json`

## Cleaned platform raster calls

The following routes/flows now use `api.raster_service_client` instead of local, repeated `httpx` blocks:

- `GET /api/v1/fields/{field_id}/available-dates`
- `GET /api/v1/fields/{field_id}/imagery/timeline`
- `POST /api/v1/fields/{field_id}/imagery/backfill`
- `GET /api/v1/fields/{field_id}/imagery/backfill/{run_id}`
- best-effort DEM terrain enrichment used by field terrain/workspace flows
- fresh NDVI read used by `POST /api/v1/fields/{field_id}/etc-dual`

## New facade client functions

- `raster_service_url()`
- `raster_service_headers()`
- `raster_get_json()`
- `raster_post_json()`
- `get_available_dates()`
- `start_imagery_backfill()`
- `get_imagery_backfill_status()`
- `get_indicator_grid()`
- `get_field_terrain()`

## Preserved behavior

- The browser still calls `sahool-platform` and never receives `X-Agent-Token`.
- Platform still verifies user permission and tenant/field ownership before proxying protected raster actions.
- `raster-service` remains the only owner/writer for raster-owned tables.
- No raster values are fabricated; failures are surfaced as HTTP errors or best-effort `None` where the previous code was already best-effort.

## Guard added

`test_p2_raster_facade_cleanup_guard.py` verifies:

1. the cleanup contract and raster facade client exist;
2. cleaned routes import the expected facade functions;
3. cleaned routes no longer open-code `RASTER_SERVICE_URL` / `httpx.AsyncClient` raster calls;
4. the facade client itself is allowlisted as the raster boundary file.

## Test results

Executed the relevant P0/P1/P1.1/P1.2/P1.3/P1.4/P2 guard and read-path suite:

```text
76 passed
```

Command:

```bash
pytest -q \
  services/sahool-platform/tests/test_p0_platform_route_ownership_guard.py \
  services/sahool-platform/tests/test_p0_db_ownership_guard.py \
  services/sahool-platform/tests/test_p0_platform_module_growth_guard.py \
  services/sahool-platform/tests/test_p1_raster_boundary_guard.py \
  services/sahool-platform/tests/test_p1_weather_boundary_guard.py \
  services/sahool-platform/tests/test_p1_decision_outcome_learning_bridge_guard.py \
  services/sahool-platform/tests/test_learning_source_lineage.py \
  services/sahool-platform/tests/test_outcome_reconciler.py \
  services/sahool-platform/tests/test_loop_referential_integrity.py \
  services/sahool-platform/tests/test_learning_summary_reconciled_outcomes.py \
  services/sahool-platform/tests/test_field_season_projection_reconciled_outcomes.py \
  services/sahool-platform/tests/test_p1_4_recommendation_to_learning_lineage_e2e.py \
  services/sahool-platform/tests/test_p2_raster_facade_cleanup_guard.py \
  tests_v9/test_learning_summary.py
```

## Deferred follow-ups

- `api/imagery_automation.py` still owns the larger background trigger flow and should be cleaned in its own extraction patch.
- `api/routers/regional_bulletin.py` still reads `zonal_stats` as a transitional read model until raster-service exposes a tenant-safe regional NDVI summary endpoint.
- Field intelligence/AI context raster aggregation should be cleaned after the field card contract is stabilized.
