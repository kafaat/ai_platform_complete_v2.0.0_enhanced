# SAHOOL v36 — Pivot Designer UI Activation

## Scope
Activated the Pivot Designer inside MapHub as a visible, map-click workflow built on top of the DrawingCore and `pivotDesigner.ts` primitives introduced in v33-v35.

## Implemented

### MapHub UI
- Added `تصميم Pivot` toggle in the main map tools row.
- Kept click-mode mutual exclusion:
  - Pivot Designer disables pins, draw/measure, and compare.
  - Draw/measure disables Pivot Designer.
  - Pins disable Pivot Designer.
  - Compare disables Pivot Designer.
- Added a Pivot Designer control panel with:
  - radius in meters
  - start angle
  - end angle
  - ring count
  - span count
  - live area/sector/circumference summary
  - clear draft designs action

### Map interaction
- Added `pivotDesignerEnabled` and `onAddPivotDraft` props to `HubMap`.
- Clicking the map in Pivot Designer mode creates a local draft `DrawFeature` of kind `pivot`.
- The draft uses the shared `buildPivotDrawFeature()` primitive, not duplicated geometry logic.
- Draft pivot sectors are rendered as dashed blue polygons on Leaflet.
- Added a map hint: `انقر على الخريطة لتحديد مركز Pivot`.

### MapLibre compatibility guard
- Extended `HubMapGLProps` to accept the v36 pivot props without breaking JSX contracts.
- Actual Pivot sector rendering is active in Leaflet MapHub; MapLibre rendering remains a later parity task.

## Files changed
- `frontend/src/sections/MapHub.tsx`
- `frontend/src/components/maphub/HubMap.tsx`
- `frontend/src/components/maphub/HubMapGL.tsx`

## Tests added
- `frontend/src/components/maphub/drawing/PivotDesignerMapHub.static.test.ts`

## Validation performed

### Frontend install/build
- `npm ci` — passed, 0 vulnerabilities.
- `npm run build` — passed.

### Frontend tests
Command:

```bash
npm test -- \
  src/components/maphub/drawing/PivotDesignerMapHub.static.test.ts \
  src/components/maphub/drawing/DrawingRemainingPhases.test.ts \
  src/components/maphub/drawing/DrawingRemainingPhases.static.test.ts \
  src/components/maphub/drawing/DrawingCore.static.test.ts \
  src/components/maphub/drawing/adapters/DrawingAdapter.static.test.ts \
  src/components/maphub/DrawingTools.static.test.ts \
  src/components/maphub/InteractiveDrawLayer.test.ts \
  src/components/maphub/weather/WeatherEngine.static.test.ts
```

Result:

```text
8 test files passed
51 tests passed
```

### Backend compile guard
- `python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core` — passed.

### Typecheck note
- `npm run typecheck` was started but did not complete within the execution timeout. No TypeScript errors were emitted before timeout. Production build and targeted/static test suite passed.

## Known limitation
The Pivot Designer currently creates local draft features. Persistent storage, backend CRUD, PostGIS validation, and timeline/audit persistence are planned for the next phases.
