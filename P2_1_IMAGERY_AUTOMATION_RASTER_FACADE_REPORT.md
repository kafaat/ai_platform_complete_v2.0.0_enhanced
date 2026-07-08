# P2.1 Imagery Automation Raster Facade Cleanup

## Scope

This patch continues P2 Raster Facade Cleanup by removing direct raster-service
HTTP transport from `services/sahool-platform/api/imagery_automation.py`.

## What changed

- Added raster facade primitives to `api/raster_service_client.py`:
  - `process_field_cdse`
  - `get_best_imagery_scene`
  - `search_imagery_scenes`
  - `process_field_from_stac`
  - `process_indicator_batch`
  - `get_job_result`
- Refactored `api/imagery_automation.py` to call those facade functions.
- Removed direct `httpx.AsyncClient`, direct `RASTER_SERVICE_URL`, and direct
  service-token/header handling from imagery automation.
- Extended the P2 guard so `api/imagery_automation.py` is treated as a cleaned
  raster boundary file.
- Added `test_p2_1_imagery_automation_raster_facade_guard.py`.

## Ownership outcome

`sahool-platform` still orchestrates *when* imagery processing is triggered, but
it no longer owns raster-service transport details in this workflow. Raster
computation, scene search, STAC processing, batch processing, and job result reads
remain behind `api.raster_service_client`, and the final owner remains
`raster-service`.

## Safety

The refactor preserves honest semantics:

- CDSE failure still falls back to Element84 path.
- No-scene and missing-band states still return `queued:false`.
- Job-result reads remain best-effort and never fabricate NDVI/NDMI/MSI values.
- Missing valid pixels still returns `None` and does not write fake statistics.
