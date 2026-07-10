# Topographic QA Test Coverage Verification — 2026-07-10

## Scope

Verified the critical Topographic QA scenarios requested for the raster-service terrain-shadow / DEM QA path.

## Coverage result

| Scenario | Status | Test coverage |
|---|---:|---|
| No DEM configured | Covered | `test_topographic_qa_is_honest_without_dem`, `test_topographic_indicator_helper_fails_closed_without_field_dem` |
| DEM available/aligned but no sun geometry | Covered | `test_topographic_risk_from_dem_computes_slope_without_sun`, `test_topographic_qa_from_aligned_dem_array_partial_without_sun_geometry` |
| DEM + sun geometry full path | Covered | `test_topographic_risk_from_dem_computes_shadow_with_sun`, `test_topographic_qa_from_aligned_dem_array_is_not_fabricated`, `test_cast_shadow_mask_detects_blocked_pixels`, `test_topographic_qa_from_aligned_dem_array_includes_cast_shadow_contract` |
| DEM alignment/open failure | Covered | `test_topographic_indicator_helper_fails_closed_on_dem_alignment_error` |

## Additional tests added in this verification

Two direct tests were added to close the remaining ambiguity:

1. `test_topographic_indicator_helper_fails_closed_without_field_dem`
   - Verifies the actual indicator helper returns `available=false` when `FIELD_DEM_PATH` is absent.
   - Confirms no fabricated mask is produced.
   - Confirms sun geometry alone does not make terrain QA available.

2. `test_topographic_qa_from_aligned_dem_array_partial_without_sun_geometry`
   - Verifies aligned DEM without sun geometry computes slope risk only.
   - Confirms shadow/hillshade/cast-shadow remain unavailable.
   - Confirms `fabricated_topographic_mask=false`.

## Verification commands

```bash
python scripts/ci/raster_topographic_qa_guard.py
PYTHONPATH=services/raster-service pytest -q \
  services/raster-service/test_raster_topographic_qa.py \
  tests_v9/test_raster_topographic_qa_guard.py \
  tests_v9/test_raster_pixel_qa_indicator_guard.py \
  tests_v9/test_raw_data_processing_contract_guard.py
```

## Results

```text
raster_topographic_qa_guard_ok
13 passed
```

## Production note

This verification proves unit and contract coverage for the four critical terrain QA paths. It does not replace a Docker/CI smoke run with a real DEM and Sentinel-derived raster.
