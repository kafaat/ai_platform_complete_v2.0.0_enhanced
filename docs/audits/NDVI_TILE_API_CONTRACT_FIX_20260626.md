# NDVI Tile API Contract Fix — 2026-06-26

## Scope
Reviewed and hardened the raster tile contract between the web map clients and `services/raster-service`.

## Confirmed existing fixes
- `db_persist.py` uses `set_config('app.current_tenant', ..., false)` for session-level tenant context across asyncpg autocommit queries.
- `HubMap.tsx`, `HubMapGL.tsx`, and `MapHub.tsx` pass `tenantId` and `imageryTs` for cache busting and layer reloads.
- Raster tile endpoints read tenant context from `X-Tenant-Id`, `tid`, or `tenant_id`.

## Additional fix applied
`/v1/fields/{field_id}/tilejson` now propagates the resolved tenant hint into the returned tile URL:

```text
/v1/fields/{field_id}/tiles/{z}/{x}/{y}.png?index=ndvi&date=latest&tid=<tenant>&v=<version>
```

This matters because MapLibre/Leaflet load returned tile URLs as image requests, not axios/fetch calls, so they cannot rely on frontend-auth headers.

## Security behavior
Resolution priority remains:

```text
X-Tenant-Id header > tid query param > tenant_id query param
```

The query tenant is a browser image-request hint, not final authorization. Field ownership checks and `fetch_latest_asset(..., tenant_id=...)` remain the isolation gate.

## Tests added
- `test_tilejson_tiles_propagate_tid_and_cache_version`
- `test_header_tenant_has_priority_over_query_tid`

## Verification
- Raster focused tests: 9/9 passed.
- `verify_review_fixes.py`: 23/23 passed.
- Python compile for raster-service files passed.
