# Ten-Capability Plan — Closable Execution

Date: 2026-07-28
Baseline: `sahool_main_01168b0_capability_plan_increment_1.zip`

## Implemented in this increment

1. **Crop Intelligence / Canonical Weather consumption** — retained increment-1 canonical GDD wiring and fail-closed compatibility boundary.
2. **Canonical Inputs / Field Digital Twin** — added `canonical_field_state.v1`, deterministic owner-product validation, evidence digests, operational eligibility, and a thin canonical-only twin projection.
3. **Yield Intelligence** — added `canonical_yield_state.v1`, validated record aggregation, bounded TrueUp calibration and explicit quality/limitations.
4. **Irrigation Recommendation** — existing canonical server-side Water/ET0/Soil path re-verified; no client depletion invention and approval boundary retained.
5. **Economics Engine** — added deterministic scenario comparison over the existing honest economic state; partial scenarios are never ranked as comparable.
6. **Offline Operations** — existing tenant-isolated queue, conflict/supersession and sync-cycle contracts re-verified.
7. **Equipment Intelligence** — added a pure fleet readiness/service-due state without claiming CAN/ISOBUS telemetry or physical execution.
8. **Decision Center Composer** — existing server-side atomic composer and PIT/provenance tests re-verified. Repository-side composer is code-complete; production cutover remains runtime-blocked.

## Honest closure matrix

| Capability | Repository closure | Remaining non-repository boundary |
|---|---|---|
| Crop Intelligence Engine | PARTIAL / advanced | CI-9 policy separation, CI-10 knowledge products, CI-11 learning |
| Canonical Weather State | CONTRACT + first production consumer CLOSED | full migration of all legacy consumers |
| Soil Closed-Loop Workspace | EXISTING PRODUCT SLICE VERIFIED | staging/runtime certification and remaining P5/P6 UI surfaces |
| Yield Intelligence | CANONICAL STATE + ingestion/calibration core CLOSED | live harvester calibration and machine consumption evidence |
| Irrigation Recommendation Engine | RECOMMENDATION PATH CLOSED IN CODE | live PG16/operator evidence and physical execution remain separate |
| Field Digital Twin | DATA MODEL / THIN VIEW CLOSED | page-by-page UI migration |
| Economics Engine | CORE + SCENARIO COMPARISON CLOSED | local price feeds/accounting reconciliation |
| Offline Operations | CORE CONTRACT CLOSED | device/network/background-worker runtime proof |
| Equipment Intelligence | READINESS/MAINTENANCE CORE CLOSED | CAN/ISOBUS telemetry and physical adapter delivery |
| Decision Center Composer | SERVER COMPOSER CLOSED IN CODE | Decision SoR role certification/cutover; remains runtime-blocked |

## Verification

```text
72 passed, 0 failed
```

Covered focused suites: canonical closures, crop canonical inputs, irrigation recommendation, yield-map ingestion, economics, offline-first and agronomic context composer.
