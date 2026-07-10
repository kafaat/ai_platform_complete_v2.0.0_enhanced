# Raster Cast-Shadow QA Implementation Report — 2026-07-10

## Decision

Continued the raster QA hardening by upgrading the previous topographic provenance layer from hillshade-based terrain risk only to a bounded DEM cast-shadow QA model when both an aligned DEM and sun geometry are available.

## What changed

### 1. Cast-shadow helper

Updated `services/raster-service/raster_topographic_qa.py` with:

- `compute_cast_shadow_mask_from_dem(...)`
- bounded up-sun horizon ray-marching
- `cast_shadow_risk_pct`
- `cast_shadow_available`
- `cast_shadow_max_steps`
- `cast_shadow_step_pixels`

The helper is explicitly bounded by `max_steps` and `step_pixels` so it remains safe for indicator preprocessing and CI.

### 2. Risk integration

`compute_topographic_risk_from_dem(...)` now combines:

- slope risk
- local hillshade risk
- bounded cast-shadow risk

When cast-shadow risk is available, the terrain shadow risk uses the stricter value between hillshade risk and cast-shadow risk.

### 3. Indicator provenance

`build_topographic_qa(...)` and `build_topographic_qa_from_dem_array(...)` now expose:

- `cast_shadow_risk_pct`
- `cast_shadow_available`
- `cast_shadow_max_steps`
- method `dem_cast_shadow_hillshade_slope` when cast-shadow is active
- `fabricated_topographic_mask = false`

### 4. Pixel quality flags

Updated `raw_data_processing.build_quality_flags(...)` and `raster_pixel_processing.py` so indicator stats can carry:

- `cast_shadow_risk_applied`
- `cast_shadow_risk_pct` inside `pixel_qa`
- existing `terrain_shadow_risk_pct` remains the combined/stricter terrain risk value

## Honesty boundary

This is still not a full physically exact terrain shadow engine. It is a bounded horizon/cast-shadow QA risk model designed for safe preprocessing.

It only activates when the required inputs are present:

- aligned DEM
- raster grid metadata
- sun azimuth
- sun altitude above horizon

If inputs are missing, the system continues to fail closed with `available=false` and never fabricates a topographic mask.

## Guards and tests

Strengthened `scripts/ci/raster_topographic_qa_guard.py` to require:

- `compute_cast_shadow_mask_from_dem`
- `cast_shadow_risk_pct`
- `cast_shadow_available`
- `cast_shadow_max_steps`
- `dem_cast_shadow_hillshade_slope`
- `cast_shadow_risk_applied`

Added tests in `services/raster-service/test_raster_topographic_qa.py` for:

- cast-shadow detection on a synthetic DEM ridge
- topographic QA envelope with cast-shadow contract

## Verification

Passed:

```text
raw_data_processing_contract_ok
raster_pixel_qa_indicator_guard_ok
raster_topographic_qa_guard_ok
route_mount_inventory_check_ok
api_versioning_policy_check_ok
contract_capabilities_schema_check_ok
health_readiness_schema_guard_ok
dependency_inventory_check_ok
dependency_conflict_inventory_check_ok
direct_dependency_bundle_check_ok
test_dependency_inventory_check_ok
```

Targeted tests:

```text
10 passed
```

## Production caveat

Docker build matrix and real DEM-backed runtime smoke are still required before production certification.
