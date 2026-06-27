# SAHOOL GIS — Timeline + Comparison Mode Implementation

## Scope
Implemented item **5. Timeline + Comparison Mode** for the advanced GIS Phase 3 package.

## What changed

### Frontend UI
- Updated `frontend/src/sections/GisToolsPage.tsx` with a new **Timeline + Comparison Mode** panel.
- The panel is read-only and explicitly non-mutating.
- It loads field geometry history from the existing backend endpoint:
  - `GET /api/v1/fields/{field_id}/geometry/history`
- It allows selecting:
  - current boundary
  - any historical geometry revision returned by the server
- It compares:
  - base area
  - comparison area
  - area delta in square meters and percent
  - vertex count delta
  - Polygon vs MultiPolygon type
- It displays a revision timeline with revision number, timestamp, and reason/source.

### API client + React Query
- Added `fetchFieldGeometryHistory()` in `frontend/src/services/api.ts`.
- Added `useFieldGeometryHistory()` in `frontend/src/hooks/useApi.ts`.
- No fake fallback was added. Backend errors remain visible in the UI.

### Pure comparison logic
- Added `frontend/src/lib/fieldGeometryTimeline.ts`.
- Supports Polygon and MultiPolygon without dropping parts.
- Normalizes geometry through the existing `fieldGeometryOps` path.
- Computes deterministic comparison metrics without server mutation.

### Tests
- Added `frontend/src/lib/fieldGeometryTimeline.test.ts`.
- Covers:
  - Polygon/MultiPolygon normalization
  - revision option ordering
  - area and vertex deltas
  - Arabic/RTL revision labels

## Validation attempted
- Attempted to run the new frontend test:
  - `cd frontend && npm test -- --run src/lib/fieldGeometryTimeline.test.ts`
- Result: not executed because dependencies are not installed in the uploaded package (`vitest: not found`, no `frontend/node_modules`).

## Notes
- Backend already had the required history endpoint and tenant/RBAC checks in `services/sahool-platform/api/routers/fields.py`.
- This implementation intentionally does not call revert or patch endpoints. It only compares revisions and leaves rollback as a separate explicit action.
