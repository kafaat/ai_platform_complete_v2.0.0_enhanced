# Raster Advanced Pixel QA Masks Continuation — 2026-07-10

## Scope

Continuation after `RASTER_PIXEL_QA_INDICATOR_PREPROCESSING_REPORT_20260709.md`.

The previous step made raw raster QA visible in indicator outputs. This step extends that QA contract so the raster path no longer treats quality as only cloud/nodata. It now carries explicit advanced mask semantics for:

- cloud
- cloud shadow
- snow/ice
- aerosol, as declared/unavailable, not fabricated
- saturation / invalid reflectance proxy
- source-native QA policy

## Files changed

```text
services/raster-service/raw_data_processing.py
services/raster-service/raster_pixel_processing.py
services/raster-service/test_raw_data_processing.py
scripts/ci/raster_pixel_qa_indicator_guard.py
RASTER_ADVANCED_PIXEL_QA_MASKS_REPORT_20260710.md
```

## What changed

### 1. Extended pixel QA score

`compute_quality_score(...)` now accepts and reports:

```text
shadow_pct
snow_pct
aerosol_pct
saturation_pct
cloud_shadow_mask_applied
snow_mask_applied
aerosol_mask_applied
saturation_mask_applied
```

It applies conservative penalties for contamination and emits warnings when a mask is detected but not applied. It remains a QA/provenance score, not an agronomic indicator.

### 2. Canonical quality flags helper

Added:

```text
build_quality_flags(...)
```

It emits:

```text
schema = sahool.raster_quality_flags/1
nodata_mask_applied
qa_layer_present
cloud_mask_applied
cloud_shadow_mask_applied
snow_mask_applied
aerosol_mask_applied
saturation_mask_applied
cloud_mask_sources
cloud_shadow_mask_sources
snow_mask_sources
aerosol_mask_sources
saturation_mask_sources
source_native_qa_policy
```

### 3. Indicator path now applies richer masks

`raster_pixel_processing.py` now derives masks as follows:

| QA item | Source | Behavior |
|---|---|---|
| Cloud | SCL 8/9/10, CLM, CLP | masks pixels |
| Cloud shadow | SCL 3 | masks pixels |
| Snow/ice | SCL 11 | masks pixels |
| Aerosol | not inferred without source QA | reported as unavailable/not fabricated |
| Saturation | reflectance range proxy | masks invalid reflectance proxy pixels |

The code intentionally does **not** pretend that aerosol masking exists without a real QA layer.

### 4. Precomputed and truecolor paths use the same quality flag schema

The precomputed index and truecolor paths now use `build_quality_flags(...)` instead of ad-hoc dictionaries.

### 5. Guards updated

`raster_pixel_qa_indicator_guard.py` now fails if advanced QA terms disappear:

```text
cloud_shadow_mask_sources
saturation_mask_sources
build_quality_flags
sahool.raster_quality_flags/1
cloud_shadow_mask_applied
saturation_mask_applied
```

## Verification

Commands run:

```bash
python -m py_compile \
  services/raster-service/raw_data_processing.py \
  services/raster-service/raster_pixel_processing.py \
  scripts/ci/raster_pixel_qa_indicator_guard.py

PYTHONPATH=services/raster-service pytest -q \
  services/raster-service/test_raw_data_processing.py \
  tests_v9/test_raster_pixel_qa_indicator_guard.py

python scripts/ci/raster_pixel_qa_indicator_guard.py
python scripts/ci/raw_data_processing_contract_guard.py
python scripts/ci/route_mount_contract_guard.py --check
python scripts/ci/api_versioning_policy_guard.py --check
python scripts/ci/test_requirements_inventory_guard.py --check
python scripts/ci/report_index_guard.py
```

Results:

```text
5 passed
raster_pixel_qa_indicator_guard_ok
raw_data_processing_contract_ok
route_mount_inventory_check_ok
api_versioning_policy_check_ok
test_dependency_inventory_check_ok
report_index_check_ok
```

## Honest remaining gaps

This is now a stronger pixel QA/provenance layer, but not yet a full atmospheric correction stack. Remaining future work:

```text
source-native aerosol QA when available
terrain-shadow QA when DEM/sun geometry are available
scene-classification-specific confidence weights by provider
station/field validation tie-in for weather-derived products
Docker build matrix evidence
```

## Verdict

```text
Raster indicators now carry richer pixel QA contracts for cloud, shadow, snow, saturation, and explicit aerosol non-fabrication.
```
