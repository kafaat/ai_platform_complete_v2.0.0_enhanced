# SAHOOL GIS Advanced Phase 3 — MultiPolygon + Geometry Versioning

## Scope
Implemented the requested GIS advanced tasks:

1. Full MultiPolygon support for field boundaries.
2. Geometry versioning operational workflow, including history review and rollback.
3. Frontend support for MultiPolygon contract and geometry history UI.

## Backend changes

- `services/sahool-platform/api/gis_geometry_guard.py`
  - Upgraded guard version to `gis-guard-v2-multipolygon`.
  - Preserves GeoJSON `MultiPolygon` instead of collapsing it to the largest `Polygon`.
  - Accepts Polygon, MultiPolygon, Feature, and multi-feature FeatureCollection.
  - Computes combined area and combined bbox across all polygon parts.
  - Validates each MultiPolygon part using the existing production polygon validator.

- `services/sahool-platform/api/geospatial_integrity.py`
  - Added MultiPolygon-aware validation for `/geometry/validate` and internal checks.
  - Keeps existing CRS, Yemen bbox, self-intersection, and area guards.

- `services/sahool-platform/api/routers/fields.py`
  - Added rollback endpoint:
    - `POST /api/v1/fields/{field_id}/geometry/revert/{revision}`
  - Reverting a geometry:
    - validates the stored revision through the same guard,
    - updates current field geometry/area/centroid,
    - appends a new geometry revision,
    - invalidates raster cache,
    - emits `FIELD_GEOMETRY_REVERTED`,
    - triggers imagery refresh best-effort.

## Frontend changes

- `frontend/src/lib/canonicalGeometry.ts`
  - Added `GeoJsonMultiPolygon` and `GeoJsonFieldGeometry`.
  - Canonical field geometry now supports Polygon or MultiPolygon.

- `frontend/src/sections/MapHub.tsx`
  - Added "سجلّ الحدود" panel for the selected field.
  - Shows recent geometry revisions.
  - Adds rollback button for older revisions.
  - Refreshes fields and imagery timestamp after rollback.

## Tests / verification

- Backend targeted tests:
  - `8 passed`
  - Covers MultiPolygon preservation, FeatureCollection merge, invalid part rejection, and existing spatial integrity tests.

- Frontend:
  - `npm run typecheck` passed.
  - `npm run build` passed.

## Notes

- MultiPolygon is now supported without silently dropping disconnected field blocks.
- Historical raster analysis can now be tied to geometry revisions rather than only the latest boundary.
- The rollback endpoint is tenant-scoped and permission-gated with `FIELD_EDIT`.
