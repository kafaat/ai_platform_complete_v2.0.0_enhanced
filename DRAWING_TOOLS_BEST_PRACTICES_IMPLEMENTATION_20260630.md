# SAHOOL Drawing Tools — Best Practices Implementation 2026-06-30

## Scope
This update applies the first safe implementation step from the drawing-tools research: a neutral DrawingCore contract. It does not replace the existing Leaflet drawing runtime, so current MapHub and field-creation flows remain stable.

## Added

- `frontend/src/components/maphub/drawing/drawingTypes.ts`
- `frontend/src/components/maphub/drawing/drawingEvents.ts`
- `frontend/src/components/maphub/drawing/drawingMeasurements.ts`
- `frontend/src/components/maphub/drawing/drawingValidation.ts`
- `frontend/src/components/maphub/drawing/DrawingProvider.ts`
- `frontend/src/components/maphub/drawing/index.ts`
- `frontend/src/components/maphub/drawing/DrawingCore.static.test.ts`
- `docs/adr/ADR-0031-drawing-tools-engine-strategy.md`

## Decision

- Keep `leaflet-draw` as the default engine for this release.
- Do not add Leaflet-Geoman as a hard dependency in this step.
- Use a feature-flag path for future engines: `VITE_DRAW_ENGINE`.
- Preserve Terra Draw/MapLibre as the portability path already present in dependencies.

## Agricultural drawing model

The new contract defines first-class agricultural feature kinds:

- field
- pivot
- management-zone
- prescription-zone
- exclusion-zone
- scout-pin
- path
- measurement

And workflows:

- create-field
- design-pivot
- split-field
- merge-fields
- create-management-zone
- create-prescription-zone
- create-exclusion-zone
- measure-area
- measure-distance

## Validation and measurements

The new pure TypeScript utilities support:

- line length
- polygon area/perimeter preview
- closed-ring validation
- coordinate validation
- pivot radius validation
- lightweight self-intersection risk detection

Backend/PostGIS validation remains the authoritative source of truth.

## Next recommended implementation

1. Add optional `LeafletGeomanAdapter` behind `VITE_DRAW_ENGINE=leaflet-geoman`.
2. Build `PivotDesigner` using the DrawingCore contract: center, radius, sectors, rings/spans, and exclusion geometry.
3. Build prescription-zone tooling with topology rules: no gaps, no overlap, inside-field only.
