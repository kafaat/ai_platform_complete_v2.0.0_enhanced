# SAHOOL Remote Sensing — RS-2/RS-3 Runtime Closure

Date: 2026-07-15
Base: `sahool_ai_platform_00da620_RS1A_remote_sensing_contracts.zip`

## Implemented

### RS-2 persistence truth
- Added `RASTER_PERSISTENCE_MODE=required|best_effort`.
- Production compose defaults to `required`.
- A single-indicator raster job is `completed` only when `raster_assets` persistence succeeds.
- Failed required persistence is terminal `failed` with `raster_asset_persistence_failed`.
- Best-effort processing is explicitly `processed_unpublished` and `publication_eligible=false`.
- Batch jobs require every successful product to be persisted before becoming `completed`.
- Added tests for required, best-effort, persisted, and invalid-mode behavior.

### RS-3 canonical observation runtime
- Upgraded indicators-service from `contract-only` to `canonical-observation-adapter`.
- It still does not compute spectral band math.
- Added canonical observation and timeline endpoints:
  - `GET /v1/fields/{field_id}/observations`
  - `GET /v1/fields/{field_id}/observation-timeline`
- Adapter consumes the existing validated raster observation bundle and emits `CanonicalObservationV1`.
- Uses legal cross-service URNs, SHA-256 lineage, versioned quality policy references, UTC timestamps, and immutable contracts.
- Added `httpx` runtime dependency and compose wiring.

### Vegetation controlled cutover
- Added `INDICATORS_SERVICE_URL`.
- Added `VEGETATION_PREFER_CANONICAL_OBSERVATIONS=1`.
- Added `VEGETATION_CANONICAL_SHADOW=1`.
- Vegetation reads canonical indicators first and retains the current raster bundle as a shadow/fallback path.
- Shadow mode compares NDVI and logs parity mismatches above `VEGETATION_CANONICAL_PARITY_TOLERANCE`.
- No direct pixel computation was introduced into vegetation.

## Validation

- Raster targeted tests: 12 passed.
- Indicators/contracts targeted tests: 14 passed.
- Vegetation targeted tests: 15 passed.
- Total targeted checks: 41 passed, 0 failed.
- Python compileall: passed.

Known pre-existing warnings:
- Three Pydantic warnings for legacy fields named `schema` in raster models.

## Not claimed complete

The following are not production-certified by this change:
- Durable indicators database and transactional NATS outbox.
- Historical canonical observation backfill.
- Baseline and anomaly models over labeled production data.
- Ground-task, decision, actuator, outcome and BFF live integration certification.
- Real-field or full-season agronomic certification.

These require live PostgreSQL/NATS/service credentials, deployment, real fields, and—in the case of agronomic certification—seasonal evidence. The repository already contains substantial decision/outcome/task capabilities, but this increment does not falsely relabel them as certified RS-4 to RS-10.
