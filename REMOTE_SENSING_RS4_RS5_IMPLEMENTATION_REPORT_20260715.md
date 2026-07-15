# SAHOOL Remote Sensing RS-4 / RS-5 Implementation Report

Date: 2026-07-15
Base: sahool_ai_platform_00da620_RS2_RS3_canonical_cutover.zip

## RS-4 — Canonical Observation Timeline and Supersession

Implemented in `services/indicators-service/observation_timeline.py` and wired into:

- `GET /v1/fields/{field_id}/observation-timeline`

Behavior:

- Reads only the real raster-service field timeseries.
- Does not recompute spectral band math.
- Converts every real point to `CanonicalObservationV1`.
- Preserves the actual acquisition date.
- Projects the latest valid observation as `published`.
- Projects older observations as `superseded`.
- Links the latest observation to the immediately previous observation through `supersedes`.
- Returns `latest_observation_refs` per indicator.
- Fails closed with HTTP 424 when no real timeline is available.

This remains a read projection until durable canonical-observation persistence is introduced.

## RS-5 — Temporal Baseline Engine

Implemented in:

- `services/vegetation-analysis-service/baseline_engine.py`
- `services/vegetation-analysis-service/routers/baselines.py`

Endpoint:

- `POST /v1/fields/{field_id}/baseline-comparisons`

Initial production-safe baselines:

1. `previous_valid`
2. `historical_robust_median`
3. `same_phenological_stage` when stage context is supplied by the canonical field-season projection

Properties:

- Consumes Canonical Observation timeline only.
- Does not query raster storage directly.
- Does not calculate NDVI or other spectral indices.
- Excludes failed-quality observations.
- Uses deterministic processing-run URNs.
- Returns expected value, deviation, deviation percentage, confidence, sample size, member observation references, and reason codes.
- Fails closed when canonical history is insufficient.

The phenology stage is deliberately accepted as a reference context rather than reimplementing GDD or crop-stage kernels inside vegetation-analysis.

## Tests

- Indicators service: 7 passed
- Vegetation baseline and regression suite: 17 passed
- Remote sensing contracts, raster persistence and observability guards: 19 passed
- Total: 43 passed, 0 failed
- Python compileall: passed

## Deliberately not claimed

- Durable database persistence for canonical observations.
- Event-driven baseline execution through NATS.
- Weather-adjusted expected-signal model.
- Peer-field cohort baseline.
- Agronomic calibration or precision certification.
- Signal anomaly lifecycle (RS-6).

These require the next increments and/or live service data.
