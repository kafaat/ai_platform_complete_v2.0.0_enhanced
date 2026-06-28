# TileJSON nginx runtime fix — 2026-06-26

Fixes the runtime log pattern where `/api/raster/v1/fields/{id}/tilejson?...&tid=...` is still logged by `sahool-platform` and returns 404.

Applied fixes:

1. `sahool-platform` compatibility proxy now preserves the full query string (`index`, `date`, `tid`).
2. `?tid=` / `?tenant_id=` is promoted to `X-Tenant-Id` when the browser image/tile request has no custom headers.
3. Default `RASTER_SERVICE_URL` changed from `http://raster-service:8001` to `http://sahool-raster-service:8001` to match docker-compose/nginx service naming.
4. `docker-compose.v9.yml` now injects `DATABASE_URL` and `REDIS_URL` into `sahool-raster-service`.
5. `asyncpg` added to raster-service requirements for DB ownership fallback.

Expected result after rebuild/recreate:

- `/api/raster/v1/fields/<id>/tilejson?index=ndvi&date=latest&tid=<tenant>` returns 200 or a truthful `available=false`, not platform 404.
- Direct nginx route remains preferred: `/api/raster/` → `sahool-raster-service`.
