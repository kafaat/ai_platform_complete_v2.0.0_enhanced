# Raster Pixel QA + Indicator Preprocessing Report — 2026-07-09

## Status
Implemented a non-breaking raster pixel QA gate for indicator processing.

## Scope
- Raw raster QA remains available at `POST /raw/process`.
- Indicator processing now carries pixel QA/provenance metadata in computed stats and job provenance.
- `ProcessRequest` and `BatchProcessRequest` expose:
  - `raw_qa_required: bool = true`
  - `min_raw_quality_score: float = 0.0`

The default threshold is permissive to avoid breaking existing flows, but the quality score is always computed and recorded.

## Runtime additions
- `services/raster-service/raw_data_processing.py`
  - Added `compute_quality_score(...)`.
  - Raw endpoint now returns `quality_flags`, `quality_score`, `spatial_alignment`, `temporal_alignment`, and unified raw-processing provenance.
- `services/raster-service/raster_pixel_processing.py`
  - Indicator pixel processing attaches `pixel_qa`, `raw_quality_score`, `quality_flags`, and `raw_qa_required`.
  - Precomputed index and truecolor paths also attach raw QA metadata.
  - If `min_raw_quality_score` is set above the computed score, processing fails with `raw_raster_quality_below_threshold` instead of silently producing a weak indicator.
- `services/raster-service/raster_job_orchestration.py`
  - Job provenance now includes `raw_processing` with `sahool.raw_processing/1`.

## Guard
Added:
- `scripts/ci/raster_pixel_qa_indicator_guard.py`
- `tests_v9/test_raster_pixel_qa_indicator_guard.py`
- `.github/workflows/raster-pixel-qa-indicator.yml`

The guard prevents indicators from losing raw QA/provenance wiring.

## Verification
Passed:
- `python scripts/ci/raster_pixel_qa_indicator_guard.py`
- `PYTHONPATH=services/raster-service pytest -q services/raster-service/test_raw_data_processing.py tests_v9/test_raw_data_processing_contract_guard.py tests_v9/test_raster_pixel_qa_indicator_guard.py`
- Core governance guards: route mount, API versioning, health/readiness, contract/capabilities, dependency inventory, dependency conflict, direct dependency bundle, report index.

## Production note
This is a preprocessing/provenance gate. It does not replace full cloud-shadow/aerosol/snow masking or live station validation. Those remain future enhancements.
