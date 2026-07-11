# Vegetation + AgriAI Completion

## Implemented

- Canonical immutable vegetation snapshot with deterministic SHA-256 lineage.
- Explicit separation of observed indices and model-derived indicators.
- Production `VEGETATION_REAL_ONLY` fail-closed mode.
- Authoritative NDVI timeseries from raster-service; no synthetic points are returned when real data is absent.
- Quality gate requiring validated real NDVI before an output is executable.
- LAI remains explicitly model-derived with algorithm and uncertainty metadata.
- Agronomic context contract covering field, season, crop, cultivar, stage, soil, irrigation, weather, vegetation and field history.
- Point-in-time leakage guard using `data_available_at/created_at` versus `decision_at`.
- AgriAI strict production mode (`AGRIAI_STRICT_CONTEXT`) blocks incomplete context.
- Vegetation snapshot hash and agronomic context hash propagate into recommendation/replay outputs.
- Irrigation profile is normalized into crop simulation management inputs.

## Runtime boundary

Raster-service remains the sole pixel-computation owner. Vegetation interprets validated products. AgriAI consumes the governed vegetation snapshot plus agronomic context and never treats synthetic vegetation as execution-grade evidence.

## Verification

- Python compilation: PASS
- Focused service tests: 39 passed
- Structural completion gate: PASS

External staging validation still requires live raster COGs, real weather/soil/history snapshots and configured service authentication.
