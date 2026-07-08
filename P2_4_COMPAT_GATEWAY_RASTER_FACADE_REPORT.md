# P2.4 Compat Gateway Raster Facade Cleanup

## Scope

This phase completes the next Raster P2 cleanup seam after P2.3 by cleaning the legacy raster passthrough in:

- `services/sahool-platform/api/routers/compat_gateway.py`

The route is intentionally retained as a narrow compatibility fallback for older nginx/compose routing where `/api/raster/*` may land on `sahool-platform`. The change makes it a BFF/compatibility alias only, not a second raster transport implementation.

## Changes

### `api/raster_service_client.py`

Added:

- `raster_get_raw(...)`

This helper centralizes:

- raster-service URL resolution;
- service-token header construction;
- optional tenant header forwarding;
- optional Authorization forwarding;
- raw byte GET for TileJSON/tile compatibility;
- safe forwarding of cache-related response headers.

### `api/routers/compat_gateway.py`

Updated `/api/raster/{path:path}` to:

- call `raster_get_raw(...)`;
- preserve browser compatibility tenant promotion from `tid` / `tenant_id`;
- stop reading `RASTER_SERVICE_URL` directly;
- stop hard-coding `sahool-raster-service`;
- stop opening a direct `httpx.AsyncClient` for raster passthrough.

Vegetation legacy passthrough was not changed in this phase because it is outside the raster boundary.

## Guard added

Added:

- `services/sahool-platform/tests/test_p2_4_compat_gateway_raster_facade_guard.py`

The guard verifies:

1. `compat_gateway.py` imports `raster_get_raw` from `api.raster_service_client`.
2. `raster_api_passthrough` does not open-code raster URL/client/token transport.
3. `raster_service_client.py` exposes raw GET support for legacy tiles.
4. `RASTER_FACADE_CLEANUP_CONTRACT.md` documents P2.4.

## Test result

Command run:

```bash
pytest -q \
  services/sahool-platform/tests/test_p2_4_compat_gateway_raster_facade_guard.py \
  services/sahool-platform/tests/test_p2_raster_facade_cleanup_guard.py \
  services/sahool-platform/tests/test_p2_1_imagery_automation_raster_facade_guard.py \
  services/sahool-platform/tests/test_p2_2_field_ai_context_raster_facade_guard.py \
  services/sahool-platform/tests/test_p2_3_field_intelligence_adapter_raster_facade_guard.py
```

Result:

```text
19 passed
```

## Result

The legacy raster compatibility route remains available but no longer owns raster transport details. Raster transport is now centralized behind `api.raster_service_client` for the cleaned P2 surfaces.
