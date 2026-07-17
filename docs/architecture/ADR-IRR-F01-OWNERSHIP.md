# ADR-IRR-F01 — Irrigation ownership and convergence boundary

Status: Accepted for IRR-F01 foundation (sliced adoption)
Date: 2026-07-17

## Decision

IRR-F01 **extends the existing irrigation runtime**. It must not introduce
parallel systems of record for assets, executions, evidence, commissioning,
dispatch, or water allocation. The reviewed IRR-FOUNDATION-01 reference package
is adopted **selectively**: only the parts that close a proven gap in the
existing runtime are built now; parts that duplicate an existing store or add a
new versioning sub-layer are deferred and expressed as queries/projections over
the existing tables instead.

| Concern | Classification | Authoritative source |
|---|---|---|
| Engineering assets | REUSE | v168 specialized irrigation tables |
| Hydraulic nodes and segments | REUSE (traverse in place) | v171 `irrigation_hydraulic_nodes` / `irrigation_hydraulic_segments` |
| Unified capability graph | REUSE | v175 `canonical_irrigation_capability_graphs` (+nodes/edges) |
| Hydraulic capability snapshot | REUSE | v171 `canonical_hydraulic_capabilities` + v175 |
| Hydraulic path / reachability | QUERY_OVER_EXISTING | traversal over persisted v171 graph — **no new closure/version tables** |
| Physical graph immutable versioning | DEFERRED | content-hash versioning (`capability_digest`) already exists; a version-chain table is a separate ADR |
| Capacity evaluation and reservation | NEW (adopted) | v195 evaluation/reservation tables — the confirmed gap |
| Field/zone → terminal-node binding | NEW (adopted, light) | v195 `irrigation_target_bindings` |
| Water allocation | REFERENCE_ONLY (not mutated) | v170 `irrigation_water_allocations` — daily-volume quota ledger; **not** altered to carry per-field flow entitlement |
| Commissioning and execution authorization | REUSE | v177 / v186 commissioning stores |
| Manual governed execution | REUSE | v187–v190 manual execution lifecycle |
| Physical as-applied delivery | REUSE | v178 as-applied runs, receipts and observations |
| Verified physical truth | REUSE (extend classification) | v178 `canonical_as_applied_irrigation_truths` — 3-way verified/partial/failed |
| Dispatch transport | REUSE | decision execution requests + actuator-service |
| Canonical execution / evidence read API | PROJECTION_OF | manual + as-applied + dispatch records |
| Provenance chain read | PROJECTION_OF | v182/v183 + v178 + v188 + v190 digests (read endpoint only) |
| Device secrets and certificates | REFERENCE_ONLY | IoT/actuator device identity registry |

## Prohibited parallel stores

No IRR migration (>= v195) may create any of the following without a superseding
ADR and explicit backfill/cutover/rollback plan:

- `irrigation_assets`
- `irrigation_executions`
- `irrigation_execution_evidence`
- a second canonical irrigation capability graph
- a third commissioning certificate store
- a second water-allocation system of record

Additionally, IRR migrations (>= v195) must **not** `ALTER TABLE
irrigation_water_allocations ... ADD COLUMN`: v170 owns that table as a
daily-volume quota ledger; per-field flow entitlement belongs on the
capacity-evaluation / target-binding side, not grafted onto the quota ledger.

## Dispatch semantics

A committed reservation and outbox record mean `dispatch_requested`, not
`dispatched`. Physical dispatch is confirmed only by the existing actuator
receipt path.

## Unit boundary

Scientific kernels may calculate with finite checked floats. Persisted legal
limits, reservations, allocated volumes, delivered volume and verification
percentages use `NUMERIC`/`Decimal`. Canonical persisted units are m³/h, m³,
kPa, seconds, mm, kW and kWh.
