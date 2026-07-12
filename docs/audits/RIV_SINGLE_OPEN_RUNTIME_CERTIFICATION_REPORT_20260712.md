# RIV Single-Open Runtime Certification

Date: 2026-07-12

## Scope

Operational completion of the Raster–Indicators–Vegetation runtime efficiency phase. The objective was to replace the previous per-indicator dataset reopen loop with a real shared-reader implementation and prove it through instrumentation.

## Implemented

- `raster_job_orchestration.run_batch_processing` now opens the source raster once per governed batch.
- One shared raster dataset is injected into the established single-indicator processing/persistence path.
- A shared per-band cache stores reflected and raw QA reads across all indicators in the batch.
- Duplicate indicators remain removed before processing.
- Independent product persistence, provenance, quality gates, and failure isolation are preserved.
- Batch jobs report:
  - `batch_io_strategy=single_dataset_open_shared_band_cache`
  - `single_open_certified=true`
  - `shared_band_cache_entries`
- Observability now exports `sahool_raster_batch_single_open_certified 1`.
- Runtime counters include the actual and expected dataset-open totals.

## Direct certification test

`test_batch_single_open_certification.py` creates a real six-band GeoTIFF and processes NDVI, NDMI, and EVI in one batch. It wraps `rasterio.open` and `DatasetReader.read` and proves:

- source dataset opens: exactly 1
- each shared source band is read: exactly 1
- all three indicators complete successfully
- the certified strategy is surfaced in job metadata

## Verification

Focused runtime/RIV suite:

`17 passed`

`py_compile` passed for all modified modules.

## Stale test note

A broader manually selected legacy test group includes old assertions that still require `indicators-service` to be `health_only/degraded`, old frontend manifest shapes, and former Vegetation fallback symbols. Those assertions contradict the already completed canonical ownership and generated-registry migration. They are stale contract tests and were not used as evidence for or against the shared-reader implementation.

## Production boundary

The single-open I/O path is now implemented and locally certified. Remaining production work is load certification with real object storage/COGs and concurrent workers, including throughput, memory pressure, GDAL block-cache behavior, and cache hit-rate measurements.
