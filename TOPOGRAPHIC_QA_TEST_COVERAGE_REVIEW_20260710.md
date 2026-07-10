# Topographic QA Test Coverage Review — 2026-07-10

## Scope

Reviewed the critical Topographic QA scenarios requested for `raster-service`:

1. No DEM configured
2. DEM configured but no sun geometry
3. DEM + sun geometry full path
4. DEM alignment/open failure graceful degradation

## Result

The first three scenarios were already covered by existing tests in:

- `services/raster-service/test_raster_topographic_qa.py`

A direct alignment/open-failure scenario was not covered explicitly. Added:

- `test_topographic_indicator_helper_fails_closed_on_dem_alignment_error`

This test sets `FIELD_DEM_PATH` to an invalid GeoTIFF-like file, passes raster grid metadata, and verifies the helper returns fail-closed topographic QA rather than throwing or fabricating a mask.

## Coverage Matrix

| Scenario | Test | Status |
|---|---|---|
| No DEM | `test_topographic_qa_is_honest_without_dem` | Covered |
| DEM without sun geometry | `test_topographic_risk_from_dem_computes_slope_without_sun` | Covered |
| DEM + sun geometry | `test_topographic_risk_from_dem_computes_shadow_with_sun` + cast-shadow tests | Covered |
| Alignment/open failure | `test_topographic_indicator_helper_fails_closed_on_dem_alignment_error` | Added and covered |

## Verification

Executed:

```bash
PYTHONPATH=services/raster-service pytest -q \
  services/raster-service/test_raster_topographic_qa.py \
  tests_v9/test_raster_topographic_qa_guard.py \
  tests_v9/test_raster_pixel_qa_indicator_guard.py \
  tests_v9/test_raw_data_processing_contract_guard.py
python scripts/ci/raster_topographic_qa_guard.py
python scripts/ci/report_index_guard.py --check
```

Results:

- `11 passed`
- `raster_topographic_qa_guard_ok`
- `report_index_check_ok`

## Certification Note

This remains static/unit coverage. Production certification still needs a Docker/CI smoke run using a real DEM and a real Sentinel scene.
