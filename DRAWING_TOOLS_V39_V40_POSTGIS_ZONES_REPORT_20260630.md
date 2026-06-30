# SAHOOL Drawing Tools v39-v40 — PostGIS Validation + Zones UI

## Base
Implemented on top of `sahool_v37_v38.zip`.

## v39 — Backend/PostGIS topology validation

Updated:
- `services/sahool-platform/api/routers/drawing_features.py`

Added:
- `PostgisTopologyValidation`
- `DrawingTopologyValidateRequest`
- `POST /api/v1/drawing-features/validate`
- `_validate_topology_postgis(...)`
- `_merge_validation(...)`

Validation coverage:
- `ST_GeomFromGeoJSON`
- `ST_IsValid`
- `ST_IsValidReason`
- `GeometryType`
- geodetic area via `ST_Area(...::geography)`
- parent-field containment via `ST_Covers`
- overlap detection with existing management/prescription/exclusion zones via `ST_Intersects` and `ST_Intersection`

Enforcement:
- Create/update rejects invalid topology with HTTP 422 `drawing_topology_invalid`.
- Persisted `validation` payload now includes the authoritative PostGIS validation result.
- Client-side validation remains feedback only; server-side PostGIS validation is authoritative.

## v40 — Management/Prescription/Exclusion Zones UI

Added:
- `frontend/src/components/maphub/drawing/zoneDesigner.ts`
- `frontend/src/components/maphub/drawing/ZoneDesigner.static.test.ts`

Updated:
- `frontend/src/components/maphub/drawing/index.ts`
- `frontend/src/components/maphub/drawing/drawingFeatureApi.ts`
- `frontend/src/components/maphub/HubMap.tsx`
- `frontend/src/sections/MapHub.tsx`

MapHub now includes:
- `Zones` toggle.
- Zone designer panel.
- zone kind selector:
  - management-zone
  - prescription-zone
  - exclusion-zone
- prescription rate + rate unit fields.
- sourceLayer binding to the active indicator layer.
- season binding when an active season exists.
- save action through `POST /api/v1/drawing-features`.
- persisted zone rendering together with pivot overlays.
- kind-specific styling:
  - management-zone: green
  - prescription-zone: amber
  - exclusion-zone: red

Current v40 UI creates an initial zone from the selected field boundary. Fine-grained split/edit remains for the next Geoman-powered editing phase.

## Validation actually run

Backend:
```bash
python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core
PYTHONPATH=services/sahool-platform python3 -m pytest -q \
  services/sahool-platform/tests/test_drawing_features_v38_static.py \
  services/sahool-platform/tests/test_drawing_features_v39_postgis_static.py
```
Result:
- Python compile guard passed
- 6 tests passed

Frontend:
```bash
cd frontend
npm ci
npm run typecheck
npm run build
npm test -- \
  src/components/maphub/drawing/DrawingCore.static.test.ts \
  src/components/maphub/drawing/adapters/DrawingAdapter.static.test.ts \
  src/components/maphub/drawing/DrawingRemainingPhases.test.ts \
  src/components/maphub/drawing/DrawingRemainingPhases.static.test.ts \
  src/components/maphub/drawing/PivotDesignerMapHub.static.test.ts \
  src/components/maphub/drawing/PivotPersistence.static.test.ts \
  src/components/maphub/drawing/ZoneDesigner.static.test.ts \
  src/components/maphub/DrawingTools.static.test.ts \
  src/components/maphub/InteractiveDrawLayer.test.ts \
  src/components/maphub/weather/WeatherEngine.static.test.ts
```
Result:
- npm ci passed, 0 vulnerabilities
- TypeScript typecheck passed
- Vite production build passed
- 10 frontend test files passed
- 58 frontend tests passed

## Known scope boundary

v40 saves a zone from the full selected field boundary as an initial workflow. Detailed vertex editing/splitting of zones should be done in the next phase by activating Geoman edit/cut/snap workflows against persisted DrawingFeature records.
