# P2 Raster Facade Cleanup Contract

## Intent

P2 moves the platform side of raster integration from scattered inline HTTP blocks
toward a single bounded facade client. The platform still verifies JWT/RBAC,
field ownership, tenant context, and UI aggregation, but it must not own raster
computation or raster state.

## Hard rules

1. `raster-service` remains the writer for raster tables and the owner of raster
   computations, COGs, indices, timelines, backfill jobs, tiles, terrain layers,
   and imagery acquisition metadata.
2. `sahool-platform` may call raster-service only through
   `api.raster_service_client` for newly cleaned routes.
3. Browser-facing platform routes may stay as compatibility/BFF routes only when
   they perform tenant/RBAC verification and then delegate to raster-service.
4. Open-coded `httpx.AsyncClient` calls to `RASTER_SERVICE_URL` are forbidden in
   the cleaned route set.
5. Any remaining direct DB reads of raster tables are transitional read models and
   must be listed in `docs/architecture/raster_boundary_allowlist.json`.

## Cleaned in this phase

- `GET /api/v1/fields/{field_id}/available-dates`
- `GET /api/v1/fields/{field_id}/imagery/timeline`
- `POST /api/v1/fields/{field_id}/imagery/backfill`
- `GET /api/v1/fields/{field_id}/imagery/backfill/{run_id}`
- fresh NDVI read used by `POST /api/v1/fields/{field_id}/etc-dual`
- best-effort DEM terrain read used by field terrain/workspace flows

## Deferred extractions

These are not moved in P2 because they are larger domain seams or require a
raster-service summary endpoint first:

- `api/imagery_automation.py`: background scene search/processing trigger.
- `api/routers/regional_bulletin.py`: transitional read of `zonal_stats` until a
  raster-service regional NDVI summary endpoint exists.
- field intelligence/AI context aggregation: read-only consumers that need their
  own follow-up cleanup once the field card contracts are stabilized.

## P2.1 — Imagery Automation Facade Cleanup

`api/imagery_automation.py` is now also a cleaned raster-boundary file.
It may orchestrate *when* to search for imagery and queue processing, but it must
not open-code raster-service transport details.

Required calls must go through `api.raster_service_client`:

- `process_field_cdse`
- `get_best_imagery_scene`
- `search_imagery_scenes`
- `process_field_from_stac`
- `process_indicator_batch`
- `get_job_result`

Forbidden in `api/imagery_automation.py`:

- direct `httpx.AsyncClient`
- direct `RASTER_SERVICE_URL`
- direct service token/header construction
- direct hard-coded `sahool-raster-service` URL

This keeps raster computation, scene search, STAC processing, batch processing,
and job result reads behind the raster facade while preserving the existing
scheduler/orchestration behavior.

## P2.2 — Field AI Context Raster Facade Cleanup

`api/routers/field_ai_context.py` is now cleaned for raster transport. It may
aggregate imagery availability and optional NDVI grid evidence into the AI
context pack, but it must not construct raster-service URLs, service-token
headers, or direct `httpx.AsyncClient` calls.

Required calls must go through `api.raster_service_client`:

- `get_available_dates`
- `get_indicator_grid`

The AI context pack remains fail-safe: raster outages or synthetic/missing grids
produce warnings and no grid evidence rather than fabricated NDVI facts.

## P2.3 — Field Intelligence Adapter Raster Facade Cleanup

`core/field_intelligence_adapters.py` is now cleaned for raster transport. It may
aggregate provider status, terrain summary, and live sensing indices into the
field-intelligence card, but it must not construct raster-service URLs or service
headers directly.

Required calls must go through `api.raster_service_client` sync fail-soft helpers:

- `get_provider_status_sync`
- `get_field_terrain_sync`
- `get_indices_sync`

The adapter remains fail-soft: raster outages return `None`, so the coordinator
can surface missing evidence instead of inventing sensing facts.



## P2.4 — Legacy Raster Compatibility Gateway Facade Cleanup

`api/routers/compat_gateway.py` keeps a narrow legacy GET fallback for
`/api/raster/{path:path}` when older nginx/compose routing accidentally sends
raster tile/TileJSON requests to `sahool-platform`.

This compatibility path is now also cleaned for raster transport:

- the router must import and call `raster_get_raw` from `api.raster_service_client`;
- the router must not read `RASTER_SERVICE_URL` directly;
- the router must not hard-code `sahool-raster-service`;
- the router must not open-code `httpx.AsyncClient` for raster passthrough;
- tenant promotion from `tid`/`tenant_id` remains in the router because it is a
  browser compatibility concern, while service URL, token/header construction,
  HTTP transport, and response header filtering live in the facade client.

This keeps the legacy raster route as a BFF/compatibility alias only, not a
second raster transport implementation.

## P2.5 — Raster Direct Wiring Final Sweep

The final raster sweep closes the remaining platform-side transport seam. From
this point onward, direct raster-service URL/token/transport wiring is allowed in
exactly one platform file:

- `api/raster_service_client.py`

Forbidden outside that file:

- `RASTER_SERVICE_URL`
- `DEFAULT_RASTER_SERVICE_URL`
- hard-coded `http://sahool-raster-service...` URLs
- direct raster-service transport/header wiring

Browser-facing `/api/raster/...` strings are not service wiring, but they are
also tightly constrained. They may appear only in:

- `api/routers/compat_gateway.py` for the legacy GET fallback;
- `api/routers/fields.py` for lazy thumbnail URLs returned to the browser;
- `api/raster_service_client.py` for the raw compatibility transport helper.

This means the remaining platform raster role is BFF/compatibility aggregation:
`raster-service` owns raster computation, raster state, COGs, TileJSON/tiles,
terrain products, and imagery processing jobs.
