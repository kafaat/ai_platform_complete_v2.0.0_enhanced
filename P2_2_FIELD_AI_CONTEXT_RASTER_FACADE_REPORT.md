# P2.2 Field AI Context Raster Facade Cleanup Report

## Scope

Cleaned the raster boundary inside:

- `services/sahool-platform/api/routers/field_ai_context.py`

This router builds the AI field context pack. It may include imagery availability
and optional NDVI grid evidence, but the platform must not wire raster-service
transport details directly.

## Changes

- Removed direct `httpx.AsyncClient` raster calls from `field_ai_context.py`.
- Removed direct `RASTER_SERVICE_URL` / `SAHOOL_AGENT_TOKEN` / `X-Agent-Token`
  construction from the AI context imagery path.
- Routed imagery date reads through `api.raster_service_client.get_available_dates`.
- Routed latest NDVI grid reads through `api.raster_service_client.get_indicator_grid`.
- Preserved fail-safe behavior: raster outage or missing/synthetic grid adds a
  warning and does not fabricate NDVI grid evidence.

## Guard added

- `services/sahool-platform/tests/test_p2_2_field_ai_context_raster_facade_guard.py`

The guard fails if `field_ai_context.py` reintroduces direct raster URL/token/httpx
wiring instead of the facade client.

## Contract updated

- `docs/architecture/RASTER_FACADE_CLEANUP_CONTRACT.md`
- `docs/architecture/raster_boundary_allowlist.json`

## Result

The AI context pack is now an aggregation/read consumer only. Raster-service
remains the owner of imagery availability, indicator-grid retrieval, COG-derived
NDVI facts, and raster quality metadata.
