# Raster Terrain-Shadow QA Implementation Report — 2026-07-10

## Summary

Continued the raster raw-processing hardening by converting the previous topographic QA provenance envelope into a real, conservative DEM-derived QA path when the required inputs are available.

This change remains fail-closed: it never fabricates topographic masks. If `FIELD_DEM_PATH`, raster grid metadata, or sun geometry are missing, the response explicitly reports unavailable terrain-shadow QA.

## Files changed

- `services/raster-service/raster_topographic_qa.py`
- `services/raster-service/raster_pixel_processing.py`
- `services/raster-service/raster_api_models.py`
- `services/raster-service/raster_job_orchestration.py`
- `services/raster-service/test_raster_topographic_qa.py`
- `scripts/ci/raster_topographic_qa_guard.py`

## Implementation details

### 1. DEM-derived topographic risk

Added pure deterministic helpers:

- `compute_topographic_risk_from_dem(...)`
- `build_topographic_qa_from_dem_array(...)`

These compute:

- `slope_risk_pct`
- `terrain_shadow_risk_pct` when sun geometry is supplied
- `hillshade_available`
- `sun_geometry_available`
- `valid_dem_pixel_ratio`
- thresholds used for reproducibility

### 2. Indicator-grid DEM alignment

`raster_pixel_processing._topographic_qa_for_indicator(...)` now attempts to align the configured DEM to the active indicator grid using `rasterio.warp.reproject` when these are available:

- `FIELD_DEM_PATH`
- raster CRS
- raster transform
- raster shape

If alignment fails, it returns an explicit unavailable envelope with `fabricated_topographic_mask=false`.

### 3. Sun geometry request contract

Added optional fields to both `ProcessRequest` and `BatchProcessRequest`:

- `sun_azimuth_deg`
- `sun_altitude_deg`

Batch processing now propagates these fields into the per-indicator `ProcessRequest`.

### 4. Guard strengthening

`raster_topographic_qa_guard.py` now checks:

- DEM risk computation helpers exist
- DEM alignment is wired into the indicator path
- request models expose sun geometry fields
- batch orchestration propagates sun geometry
- provenance still forbids fabricated terrain masks

## Verification

Executed successfully:

```text
python scripts/ci/raster_topographic_qa_guard.py
python -m py_compile services/raster-service/raster_topographic_qa.py services/raster-service/raster_pixel_processing.py services/raster-service/raster_api_models.py services/raster-service/raster_job_orchestration.py scripts/ci/raster_topographic_qa_guard.py tests_v9/test_raster_topographic_qa_guard.py
PYTHONPATH=services/raster-service pytest -q services/raster-service/test_raster_topographic_qa.py tests_v9/test_raster_topographic_qa_guard.py
python scripts/ci/raster_pixel_qa_indicator_guard.py
python scripts/ci/raw_data_processing_contract_guard.py
python scripts/ci/route_mount_contract_guard.py --check
python scripts/ci/api_versioning_policy_guard.py --check
python scripts/ci/contract_capabilities_schema_guard.py --check
python scripts/ci/health_readiness_schema_guard.py
python scripts/ci/dependency_inventory_guard.py --check
python scripts/ci/service_dependency_conflict_guard.py --check
python scripts/ci/build_service_dependency_bundle.py --check
python scripts/ci/test_requirements_inventory_guard.py --check
```

Focused tests:

```text
6 passed
```

## Production note

This is a terrain-shade QA metric, not full cast-shadow ray tracing. Full cast-shadow modeling still requires a dedicated solar geometry + DEM ray casting implementation. The current version is intentionally conservative and honest.
