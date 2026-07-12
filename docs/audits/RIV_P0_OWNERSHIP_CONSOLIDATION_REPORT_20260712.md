# RIV P0 Ownership Consolidation Report — 2026-07-12

## Scope
First implementation increment for Raster–Indicators–Vegetation consolidation.

## Implemented
- Added canonical ownership manifest: `shared/contracts/indicator_ownership.json`.
- Declared raster-service as the sole owner of observed spectral products.
- Declared vegetation-analysis-service as interpretation owner.
- Declared sahool-platform as dashboard aggregation owner.
- Removed executable `compute_ndvi_from_bands` kernel from sahool-platform spatial pipeline.
- Converted indicators-service from a misleading health-only phantom into a contract-only runtime:
  - readiness is honest and limited to ownership/catalog publication;
  - spectral compute remains fail-closed;
  - added ownership and catalog endpoints.
- Quarantined direct Sentinel-Hub vegetation computation behind `LEGACY_DIRECT_SENTINEL_ENABLED=false` by default.
- Corrected frontend labels so the contract service is not presented as the compute/data owner.
- Added CI guards for:
  - single owner per product;
  - no platform NDVI kernel;
  - no spectral formula outside the explicit allowlist;
  - truthful frontend consumer labels;
  - default-off legacy direct provider path.

## Verification
- RIV ownership/boundary suite: 18 passed.
- Vegetation + Indicators + new RIV guards: 60 passed.
- Python compilation passed for modified Python modules.

## Deliberate temporary exception
`sentinel_hub/vegetation_real.py` remains in the formula allowlist only as a quarantined legacy path. It is disabled by default and must be migrated into raster-service adapters or deleted in RIV-P1.

## Next increment
RIV-P1 Canonical Indicator Contract and Registry Generation:
1. Generate platform/frontend/vegetation capability views from the canonical manifest.
2. Remove independent indicator registries.
3. Separate raw raster time series from vegetation interpretation endpoints.
4. Add producer-consumer orphan and ownership-conflict inventory gates.
