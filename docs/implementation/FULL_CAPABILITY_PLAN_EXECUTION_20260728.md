# SAHOOL capability plan — execution checkpoint (2026-07-28)

## Executed in this increment

1. **Release evidence integrity** — fixed the archive-binding CLI tautology. Check mode no longer rewrites the sidecar it verifies.
2. **Canonical Weather → Crop Intelligence (WX-10 / CI-7)** — Crop Intelligence now prefers `CanonicalWeatherState.products.gdd`, propagates state/snapshot evidence IDs, fails closed for a non-canonical supplied weather state, and marks scalar GDD as an explicit compatibility bridge.
3. **Knowledge boundary** — when the caller does not provide `gdd_to_maturity`, Crop resolves it from the versioned crop card rather than inventing a threshold.

## Verified existing capability surfaces

The repository already contains substantial implementations and tests for Soil Closed Loop, yield-map ingestion, field irrigation recommendation, economics state, offline contracts, equipment inventory, and the crop→decision candidate boundary. Focused regression suites were run rather than claiming these domains were absent.

## Honest closure state

| Requested item | Current result |
|---|---|
| Crop Intelligence Engine | **Advanced, not fully closed** — canonical weather input boundary implemented; policy/knowledge/learning seams remain. |
| Canonical Weather State | **Implemented foundation, not fully migrated** — state product and views exist; all production consumers have not been migrated. |
| Soil Closed-Loop Workspace | **Substantial code exists; runtime/product closure not re-certified here.** |
| Yield Intelligence | **Yield ingestion and analysis exist; machine/runtime calibration remains outside this increment.** |
| Irrigation Recommendation Engine | **Field-level canonical consumer exists and tests pass; live data/runtime proof remains environment-dependent.** |
| Field Digital Twin | **Absorbed into CI-7 canonical input contracts; no second parallel twin model was created.** |
| Economics Engine | **Existing economic state/intelligence tests pass; comprehensive product audit still required.** |
| Offline Operations | **Existing offline-first contracts and tests present; device/network runtime certification not produced in sandbox.** |
| Equipment Intelligence | **Inventory/export foundations exist; physical CAN/ISOBUS delivery and consumption remain open by registry contract.** |
| Decision Center Composer | **Not falsely closed** — remains `BLOCKED-DESIGN+RUNTIME`; requires server-side composer, atomic AgronomicContext, and Decision SoR role/runtime certification. |

## Non-negotiable external blockers

- `DECISION-SOR-CUTOVER-WIRING-01`: database role topology and live cutover proof.
- `RUNTIME-FUNCTIONAL-LIVE-PROOF`: trusted `staging-pg16` runner and signed runtime evidence.
- `INT-004B/C`: physical device transport and machine-consumption confirmation.

These cannot be truthfully generated from this source archive or sandbox.
