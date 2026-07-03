# SAHOOL — Segmentation Remaining Completion (2026-07-03)

## Scope
Implemented the remaining high-value production improvements after basemap + SAM2 polygon hardening:

1. Client-side boundary refinement controls in `AddFieldWithMap`.
2. Live operator gate for the complete platform segmentation route.
3. Static regression tests to lock the UI/refinement/live-gate contract.

## Changes

### Frontend — boundary review tools
File: `frontend/src/components/AddFieldWithMap.tsx`

Added:
- Boundary source/vertex/confidence summary.
- Three client-side refinement levels:
  - light: 1m
  - recommended: 3m
  - strong: 5m
- Local Douglas-Peucker simplification in meter space.
- Near-duplicate vertex cleanup.
- Undo/redo remains active because each refinement pushes a history snapshot.
- `boundary_metadata` is updated with:
  - `client_refined`
  - `client_refine_level`
  - `client_simplify_tolerance_m`
  - `vertices_before_client_refine`
  - `vertices_after_client_refine`

This is intentionally a review/assist tool only. The backend save guard remains the source of truth.

### Live E2E operator gate
File: `scripts/e2e/segmentation_platform_live_gate.py`

Added a live gate that exercises the production trust boundary:

`nginx /api/segmentation/ -> sahool-platform -> field-segmentation -> SAM2`

Environment:
- `SAHOOL_BASE_URL=https://localhost`
- `SAHOOL_JWT=<user jwt>`
- `SEGMENTATION_MODE=auto|hybrid|manual`
- `SEGMENTATION_BBOX=minLon,minLat,maxLon,maxLat`
- `SEGMENTATION_REQUIRE_MODEL=true|false`
- `SAM2_BASE_URL=http://localhost:8080`

Use `SEGMENTATION_REQUIRE_MODEL=true` when SAM2 weights are mounted and `/readyz` reports `model_loaded=true`.

### Tests
File: `tests_v9/test_segmentation_remaining_ui_live_gate_20260703.py`

Locks:
- Boundary improvement controls exist.
- Live gate uses `SAHOOL_JWT`, `/api/segmentation/segment`, and SAM2 readiness.
- Manual fallback metadata remains intact.

## Verification performed

- `python -m pytest tests_v9/test_segmentation_remaining_ui_live_gate_20260703.py tests_v9/test_segmentation_boundary_metadata_contract_20260703.py tests_v9/test_field_geometry_save_guard_20260703.py tests_v9/test_mapbox_basemap_contract_20260703.py -q`
  - PASS: 13 passed
- `cd frontend && npm ci --no-audit --no-fund && npm run typecheck -- --pretty false`
  - PASS
- `cd frontend && npm test -- --run src/lib/layerRegistry.test.ts src/services/api.test.ts`
  - PASS: 25 passed
- `python scripts/ci/v9_gpu_contract_gate.py`
  - PASS
- `python scripts/ci/v9_feature_transfer_gate.py`
  - PASS
- `python scripts/ci/service_port_gate.py`
  - PASS
- `bash scripts/production_validation_gate.sh`
  - PASS; Python compile compiled=1658 failed=0

## Notes

- Google tiles remain disabled unless a future official Google Map Tiles API session-token integration is implemented.
- SAM2 live model-backed path still requires runtime weights and `model_loaded=true` on the target machine.
- BYPASSRLS warnings are pre-existing approved warnings in the production gate and did not fail validation.
