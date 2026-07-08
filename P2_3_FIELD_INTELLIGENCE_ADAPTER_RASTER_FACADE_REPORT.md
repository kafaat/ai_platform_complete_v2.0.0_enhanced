# P2.3 Field Intelligence Adapter Raster Facade Cleanup

## Scope

Cleaned `services/sahool-platform/core/field_intelligence_adapters.py` so field-intelligence live context no longer wires raster-service transport directly.

## Changes

- Added sync, fail-soft raster facade helpers in `api/raster_service_client.py`:
  - `raster_get_json_sync`
  - `get_provider_status_sync`
  - `get_field_terrain_sync`
  - `get_indices_sync`
- Replaced direct provider-status, terrain, and `/indices` calls in `core/field_intelligence_adapters.py` with facade calls.
- Added a static guard to prevent regression to direct `RASTER_SERVICE_URL` / hard-coded service URL wiring.

## Safety

No production raster computation was moved into platform. The platform remains a fail-soft consumer: raster failures return `None` and downstream evidence remains explicitly missing.
