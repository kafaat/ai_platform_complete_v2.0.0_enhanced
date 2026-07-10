# CLP All-NaN Test Compatibility Fix — 2026-07-10

## Scope

Updated the CLP all-NaN edge-case test after cloud masking moved from inline logic in `raster_pixel_processing.py` into strategy execution in `raster_cloud_mask_strategies.py`.

## Change

Updated:

- `tests_v9/test_raster_pixel_processing_edge_cases.py`

The test now checks the combined source of:

- `services/raster-service/raster_pixel_processing.py`
- `services/raster-service/raster_cloud_mask_strategies.py`

This keeps the test aligned with the architecture: the CLP handling logic now belongs to `Sentinel2SCLStrategy`, while `raster_pixel_processing.py` consumes the strategy result.

## Verified CLP behavior

The test now verifies:

- `finite = np.isfinite(clp_f)` exists
- `if bool(np.any(finite))` guards `np.nanmax`
- `clp_max = float(np.nanmax(clp_f))` only executes after the finite guard
- `np.where(finite, clp_f >= threshold, False)` prevents NaN values from becoming true cloud pixels
- `sentinel2_clp_all_nan_unavailable` records the all-NaN condition honestly

## Validation

Executed:

```bash
PYTHONPATH=services/raster-service pytest -q \
  tests_v9/test_raster_pixel_processing_edge_cases.py \
  services/raster-service/test_cloud_mask_strategies.py \
  tests_v9/test_raster_validated_product_guard.py

python scripts/ci/raster_validated_product_guard.py
python scripts/ci/raster_pixel_qa_indicator_guard.py
python scripts/ci/raw_data_processing_contract_guard.py
python scripts/ci/report_index_guard.py --check
```

Result:

- `10 passed`
- `raster_validated_product_guard_ok`
- `raster_pixel_qa_indicator_guard_ok`
- `raw_data_processing_contract_ok`
- `report_index_check_ok`

## Production note

This is a test compatibility fix only. It does not add dependencies, routes, or runtime behavior changes.
