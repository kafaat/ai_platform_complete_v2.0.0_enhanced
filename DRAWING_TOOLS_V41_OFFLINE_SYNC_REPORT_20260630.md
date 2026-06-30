# SAHOOL v41 — Offline Drawing Drafts + Sync Queue

## Scope
Implemented the next drawing-tools phase on top of `sahool_v39_v40.zip`: offline-first drawing drafts and a deterministic sync queue contract for Pivot, Management Zone, Prescription Zone, Exclusion Zone, and future drawing features.

## Added files

- `frontend/src/components/maphub/drawing/drawingOfflineSync.ts`
- `frontend/src/components/maphub/drawing/DrawingOfflineSync.test.ts`
- `frontend/src/components/maphub/drawing/DrawingOfflineSync.static.test.ts`

## Updated files

- `frontend/src/components/maphub/drawing/drawingFeatureApi.ts`
- `frontend/src/components/maphub/drawing/index.ts`
- `frontend/src/sections/MapHub.tsx`

## Capabilities

- Safe localStorage guards for browser/offline mode.
- Local draft persistence by field.
- Sync queue with operation IDs.
- Queue item statuses: `pending`, `syncing`, `failed`, `synced`.
- Create/update/delete queue entries.
- Offline-aware list wrapper that merges remote features with queued local create features.
- Offline-first create/update/delete wrappers that preserve the existing MapHub workflow while queuing network failures.
- Injected sync client API for testability and future background sync service worker integration.
- Exported offline utilities from DrawingCore barrel.

## MapHub integration

`MapHub.tsx` now aliases the offline-first wrappers behind the existing local function names:

- `createDrawingFeatureOfflineFirst as createDrawingFeature`
- `listDrawingFeaturesWithOfflineQueue as listDrawingFeatures`

This keeps current Pivot and Zone workflows stable while adding offline fallback.

## Validation run

### Frontend

- `npm ci` — passed, 0 vulnerabilities.
- `npm run typecheck` — passed.
- `npm run build` — passed.
- Drawing/weather test subset:
  - 12 test files passed.
  - 65 tests passed.

### Backend

- `python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core` — passed.
- `PYTHONPATH=services/sahool-platform python3 -m pytest -q services/sahool-platform/tests/test_drawing_features_v38_static.py` — 3 passed.

## Limitations / next phase

This is a frontend offline queue contract with localStorage persistence and API wrappers. The next phase should add:

- v42: visible sync status badges and manual “sync now” action in MapHub.
- v43: service-worker/background sync when available.
- v44: conflict resolution UI for server-side geometry version conflicts.
