# ADR-0031 — Drawing tools engine strategy for SAHOOL

## Status
Accepted for phased implementation.

## Context
SAHOOL already uses Leaflet, React 19, `leaflet-draw`, MapLibre, and Terra Draw. The current drawing implementation is functional and stable for field creation, measurement, and basic editing, but modern agricultural platforms need more than generic geometry tools.

Benchmarked product patterns:

- Valley-style pivot workflows emphasize center pivot design, radius, sectors, spans/rings, irrigation windows, and operational control.
- FieldView-style prescription workflows emphasize field boundaries, management zones, prescriptions, applied rates, crop/season context, and operational auditability.
- Enterprise GIS workflows require topology validation, snapping, measurement, edit history, offline drafts, and server-side geometry validation.

## Decision
Do not replace Leaflet immediately. Introduce a DrawingCore contract first, then migrate tools behind adapters.

Recommended path:

1. Keep `leaflet-draw` as the stable default engine.
2. Add a Leaflet-Geoman adapter in a dedicated PR for richer editing, snapping, cutting, rotating, and measurement.
3. Keep Terra Draw available for future MapLibre/OpenLayers portability.
4. Build agricultural workflows above the drawing engine rather than exposing generic geometry buttons only.

## Target architecture

```text
DrawingCore
  ├── LeafletDrawAdapter        current/default
  ├── LeafletGeomanAdapter      next recommended adapter
  ├── TerraDrawAdapter          portability path
  └── MapLibreTerraDrawAdapter  vector-tile/WebGL path
```

Unified events:

```text
draw:start
draw:vertex-change
draw:created
draw:edited
draw:deleted
draw:validated
draw:measurement-change
draw:draft-save
draw:commit
draw:cancel
```

## Agricultural workflows

SAHOOL drawing tools should be task-first:

- Create field
- Design Pivot
- Split/Merge field
- Create management zone
- Create prescription zone
- Create exclusion zone
- Measure area/distance

Each committed geometry should carry crop, season, source layer, confidence, operation id, version, and audit metadata.

## Validation policy

Client-side validation gives immediate feedback. Backend PostGIS validation remains authoritative.

Required rules:

- Valid GeoJSON geometry.
- Closed polygon rings.
- Minimum vertex count.
- Area thresholds.
- Pivot radius thresholds.
- Zone inside field.
- Optional no-overlap/no-gap rules for management and prescription zones.
- Audit trail for geometry changes.

## Consequences

Benefits:

- No hard dependency switch in one risky step.
- Leaflet UI remains stable while richer engines are introduced gradually.
- Terra Draw and MapLibre can be adopted later without rewriting agricultural workflows.
- Pivot and prescription tools become first-class product features, not generic shapes.

Trade-offs:

- One additional abstraction layer.
- Geoman adapter still requires a dedicated implementation and dependency decision.
- Topology rules must be duplicated lightly on the client and authoritatively on the backend.
