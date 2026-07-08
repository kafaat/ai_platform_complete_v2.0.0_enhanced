# P2.5 Raster Direct Wiring Final Sweep Report

## Scope

Final sweep after P2.4 to prevent raster-service transport details from spreading
inside `sahool-platform`.

## Implemented

- Added `services/sahool-platform/tests/test_p2_5_raster_direct_wiring_final_sweep.py`.
- Updated `docs/architecture/raster_boundary_allowlist.json` with:
  - `direct_service_wiring_allowed_files`
  - `browser_api_raster_alias_allowed_files`
  - `final_sweep_status`
- Updated `docs/architecture/RASTER_FACADE_CLEANUP_CONTRACT.md` with the P2.5
  hard rules.

## Final rule

Only `api/raster_service_client.py` may read/construct direct raster-service URL,
default service host, service token headers, tenant forwarding headers, or raw
raster transport.

`/api/raster/...` browser aliases are allowed only in:

- `api/routers/compat_gateway.py`
- `api/routers/fields.py`
- `api/raster_service_client.py`

## Result

The final sweep now makes direct raster wiring a CI-visible violation instead of
a convention.
