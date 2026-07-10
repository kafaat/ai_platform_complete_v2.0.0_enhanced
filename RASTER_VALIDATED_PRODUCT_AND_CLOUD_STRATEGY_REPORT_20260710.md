# Raster Validated Product + Cloud Mask Strategy Report — 2026-07-10

## Decision

Implemented the explicit `ValidatedRasterProduct` contract and source-specific cloud mask strategy contracts for raster indicator preprocessing.

## Why

Cloud masking cannot be a single boolean. Sentinel-2 uses SCL/CLM/CLP-like QA, Landsat uses QA_PIXEL bits, and drone orthomosaics may not have native cloud QA. Indicators also need an explicit validated product envelope rather than implicitly trusting raw pixels.

## Added

- `services/raster-service/raster_validated_product.py`
- `services/raster-service/raster_cloud_mask_strategies.py`
- `services/raster-service/test_raster_validated_product.py`
- `scripts/ci/raster_validated_product_guard.py`
- `tests_v9/test_raster_validated_product_guard.py`
- `.github/workflows/raster-validated-product.yml`

## Contract

`ValidatedRasterProduct` requires:

- `quality_score`
- `valid_pixel_ratio`
- `cloud_mask_applied`
- `shadow_mask_applied`
- `reflectance_normalized`
- `spatial_crs`
- `quality_flags` using `sahool.raster_quality_flags/1`
- `pixel_qa` using `sahool.raster_pixel_qa/1`
- `provenance`
- explicit `cloud_mask_strategy`

If cloud mask is not applied, the product must use an explicit no-op/provider strategy such as:

- `noop_unavailable`
- `provider_precomputed_expected`
- `rgba_alpha_mask`
- `unknown_unavailable`

This prevents silent unmasked indicator products.

## Cloud Mask Strategy Contract

Added:

- `CloudMaskStrategy`
- `Sentinel2SCLStrategy`
- `LandsatQAPixelStrategy`
- `NoOpCloudMaskStrategy`
- `strategy_for_source_format(...)`

This establishes the strategy pattern before expanding raster providers.

## Indicator Path Wiring

`raster_pixel_processing.py` now writes `validated_raster_product` into stats for:

- precomputed single-band indicators
- precomputed truecolor
- full band-math indicator processing

The indicator path calls `assert_indicator_accepts_validated_product(...)` before publishing stats/provenance.

## Guard

`raster_validated_product_guard.py` fails if:

- `ValidatedRasterProduct` disappears
- cloud strategy classes disappear
- indicator path stops emitting `validated_raster_product`
- `BandMapping.qa_pixel` disappears
- runtime smoke stops running the guard

## Verification

Executed:

```bash
python scripts/ci/raster_validated_product_guard.py
python scripts/ci/raster_pixel_qa_indicator_guard.py
python scripts/ci/raster_topographic_qa_guard.py
python scripts/ci/raw_data_processing_contract_guard.py
PYTHONPATH=services/raster-service pytest -q \
  services/raster-service/test_raster_validated_product.py \
  tests_v9/test_raster_validated_product_guard.py \
  tests_v9/test_raster_pixel_qa_indicator_guard.py \
  tests_v9/test_raster_topographic_qa_guard.py
PYTHONPATH=services/raster-service pytest -q \
  services/raster-service/test_raw_data_processing.py \
  services/raster-service/test_raster_topographic_qa.py \
  tests_v9/test_raw_data_processing_contract_guard.py
```

Results:

- `raster_validated_product_guard_ok`
- `raster_pixel_qa_indicator_guard_ok`
- `raster_topographic_qa_guard_ok`
- `raw_data_processing_contract_ok`
- `6 passed`
- `15 passed`

## Honest limitation

The current cloud strategy contract is established and tested. The existing indicator path still uses its current SCL/CLM/CLP masking logic, but now emits the validated product contract. A later provider-expansion phase can replace the inline mask logic with strategy execution without changing the outward contract.
