# RIV Runtime Efficiency Certification — Continuation

Date: 2026-07-12

## Scope

Continuation of Raster–Indicators–Vegetation consolidation, focused on runtime duplicate suppression, worker contention, observability, and truthful performance certification.

## Forensic finding

The existing batch endpoint grouped several indicators under one job, but it still invoked the single-indicator processor once per unique indicator. That processor opens the raster dataset independently for every indicator. Therefore, the previous wording implying one physical dataset open was not operationally proven.

The implementation now exposes this honestly as:

`batch_io_strategy = per_indicator_dataset_open`

and exports:

`sahool_raster_batch_single_open_certified 0`

No production certification may claim single-open processing while this value is zero.

## Implemented hardening

### Cluster-safe batch claim

Added `services/raster-service/indicator_batch_claim.py`.

The deterministic claim includes:

- tenant
- field
- scene and acquisition time
- raster source
- normalized indicator set
- band mapping
- geometry hash and revision
- cloud-mask policy
- raw QA policy and threshold

Redis uses `SET NX EX` so concurrent replicas converge on one canonical job. Duplicate callers receive the existing authoritative `job_id` rather than starting another computation. The in-memory fallback is explicitly replica-local.

Claim release uses compare-and-delete and cannot release a different worker's claim.

### Duplicate indicator removal

Batch orchestration now normalizes and removes duplicate indicators while preserving first-request order. Job state records requested, unique, and removed counts.

### Observability

Added process counters for:

- claims acquired
- claims deduplicated
- batch jobs started/completed/failed
- requested/unique/deduplicated indicators
- indicator successes/failures
- expected dataset opens

The metrics endpoint exports these as `sahool_raster_batch_*`.

### Configuration

Added `RASTER_BATCH_CLAIM_TTL_SECONDS=86400` to `.env.example`.

## Verification

Focused tests: 9 passed.

Expanded RIV and raster contract suite: 33 passed.

The parallel-claim test launches 64 concurrent claims and proves exactly one winner and one canonical job id.

## Remaining runtime optimization

A dedicated shared-reader implementation is still required to make this sequence true:

`open scene once -> load each required band once -> compute all indicators -> persist independent products`

Until that implementation and a rasterio-open-count test pass, the service correctly reports single-open certification as false.
