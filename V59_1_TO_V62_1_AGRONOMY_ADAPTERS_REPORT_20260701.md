# V59.1–V62.1 — Agronomy Adapter Chain (real engines, replaceable, fail-safe)

Strengthens the agronomic reality of the agent tools per the "replaceable adapter, not
hard dependency; proposal → human confirmation → approval-gated write" principle.
Every phase keeps its agent tool schema and prior contract tests unchanged, ships a
deterministic in-sandbox core, gates any heavy/real model behind operator env + fail-safe,
and keeps everything proposal-only.

## v59.1 — Boundary adapter chain + 7-signal quality
`field_boundary_backends.py` + `field_boundary_ai.propose_boundaries`
- Best-first chain: `registered_boundary_lookup → ftw_boundary_adapter → sentinel2_boundary_fallback → bbox_fallback`.
- 7-signal quality: boundary_confidence, edge_strength, shape_validity, area_reasonableness,
  source_resolution_m, cloud_risk, requires_user_confirmation.
- Guard: `degraded_to_bbox_despite_imagery` when imagery exists but was unusable (e.g. cloud).
- FTW gated (weights+torch); real inference needs operator env. Licensing: FTW code MIT;
  some FTW weights CC-BY-NC-SA (audit); Delineate Anything AGPL-3.0 rejected.

## v60.1 — NDVI-grid k-means productivity zoning
`productivity_zones_clustering.py` + `propose_productivity_zones`
- Deterministic 1-D k-means on an NDVI grid → per-class zone polygons + cluster_separability.
- Opt-in on `ndvi_grid`; falls back to the v60 strip proposal when absent. Pure Python.

## v61.1 — Soil-sampling grid / zone / hybrid
`soil_sampling_strategies.py` + `plan_soil_sampling`
- `sampling_strategy` (default `zone` = v61): `grid` (regular coverage), `hybrid` (zone + grid infill).
- `recommended_samples_for_area` advisory (~1 core/2 ha, floor 3, cap 20).

## v62.1 — Prescription export adapters
`prescription_export_adapters.py` + VRA engine advertising
- Formats: `geojson`, `csv`, `isoxml` (ISOBUS TaskData skeleton), `shp_attributes` (GDAL-downstream).
- Every payload `machine_executable=False` / `requires_approval=True` — preview only; the VRA
  engine advertises formats but never flips `ready_for_machine_export`. Export stays the
  `create_prescription_map` high-risk approval + agronomist review.

## Governance invariant (all phases)
detected/derived → **proposal** (requires_user_confirmation) → human confirmation →
approval-gated write. No adapter auto-saves, auto-exports, or executes.

## Verification
- 30 new deterministic tests across the four phases; every prior contract test unchanged;
  full unit gate 2157 passed; app constructs (14 routes); ruff + defect-signatures clean.
  MapHub TrueColor default and the harness governance untouched.

## Operator env needed for the real (non-sandbox) half
- v59.1: `SAHOOL_FTW_WEIGHTS` + torch + `_run_ftw_inference` wiring (S2 tile → mask); optional rasterio.
- v60.1: supply a real NDVI grid (multi-temporal composite) via params/evidence.
- v62.1: GDAL/pyshp for binary shapefile; equipment adapter for full ISOXML controller export.
