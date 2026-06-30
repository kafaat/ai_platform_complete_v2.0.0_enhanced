# SAHOOL Drawing Tools v37-v38 — Pivot Season Binding + Backend CRUD

## Base
- Source package: `sahool_v36.zip`

## v37 — Pivot binding to field/season
- `MapHub.tsx` now derives `selectedActiveSeasonId` from `active_season`, `current_season`, or active season list.
- Pivot drafts created by clicking the map are now stamped with:
  - `properties.fieldId`
  - `properties.seasonId` when an active season is discoverable
  - `properties.workflow = design-pivot`
- The Pivot Designer panel shows a season linkage badge.

## v38 — Drawing Feature Backend CRUD
Added tenant-scoped API router:

- `services/sahool-platform/api/routers/drawing_features.py`

Endpoints:

- `GET /api/v1/fields/{field_id}/drawing-features`
- `POST /api/v1/drawing-features`
- `PATCH /api/v1/drawing-features/{feature_id}`
- `DELETE /api/v1/drawing-features/{feature_id}`

Security and tenancy:

- Read routes require `FIELD_VIEW`.
- Mutating routes require `FIELD_EDIT`.
- All queries are scoped by `tenant_id`.
- Field ownership is checked before listing or saving field-linked features.
- Deletes are soft deletes via `deleted_at`.

Storage:

- Creates `drawing_features` table if it does not exist.
- Stores GeoJSON geometry, properties, measurements, validation, draft flag, version, timestamps, saved_by.
- Supports JSONB-safe decoding for asyncpg/jsonb codec differences.

Frontend integration:

- Added `frontend/src/components/maphub/drawing/drawingFeatureApi.ts`.
- MapHub loads persisted pivot features for the selected field.
- MapHub can save local pivot drafts to the backend using `createDrawingFeature`.
- Saved and draft pivots are rendered together when the pivot overlay is enabled.

## Validation executed

Backend:

```bash
python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core
PYTHONPATH=services/sahool-platform python3 -m pytest -q services/sahool-platform/tests/test_drawing_features_v38_static.py
```

Result:

- Python compile guard passed.
- Backend static CRUD contract tests: `3 passed`.

Frontend:

```bash
cd frontend
npm ci
npm run build
npm test -- \
  src/components/maphub/drawing/DrawingCore.static.test.ts \
  src/components/maphub/drawing/adapters/DrawingAdapter.static.test.ts \
  src/components/maphub/drawing/DrawingRemainingPhases.test.ts \
  src/components/maphub/drawing/DrawingRemainingPhases.static.test.ts \
  src/components/maphub/drawing/PivotDesignerMapHub.static.test.ts \
  src/components/maphub/drawing/PivotPersistence.static.test.ts \
  src/components/maphub/DrawingTools.static.test.ts \
  src/components/maphub/InteractiveDrawLayer.test.ts \
  src/components/maphub/weather/WeatherEngine.static.test.ts
```

Result:

- `npm ci` passed, 0 vulnerabilities.
- Vite production build passed.
- Frontend tests: `9 test files passed`, `54 tests passed`.

Note:

- `npm run typecheck` full project run started but exceeded the execution timeout. The production build completed successfully.
