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

Additionally — the ban here is **precise, not blanket**. A benign `ALTER TABLE
irrigation_water_allocations ADD COLUMN` (e.g. an audit/comment column) is fine.
What is forbidden is turning v170's **daily-volume quota ledger** into a
per-field **flow/priority allocation** system of record: IRR migrations (>= v195)
must not ADD flow/priority entitlement columns (`allocated_flow_m3h`,
`priority`, `allocation_basis`, `allocation_share_pct`, per-field `farm_id`/
`field_id`). That entitlement belongs on the capacity-evaluation / target-binding
side.

The guard also forbids, for migrations >= v195: a new canonical
hydraulic-capability SoR competing with v171/v175, and the deferred
topology-version / path-closure tables (they need a superseding ADR — the
hydraulic path is answered by a query over the existing v171 graph).

## Dispatch semantics

A committed reservation and outbox record mean `dispatch_requested`, not
`dispatched`. Physical dispatch is confirmed only by the existing actuator
receipt path.

## Unit boundary

Scientific kernels may calculate with finite checked floats. Persisted legal
limits, reservations, allocated volumes, delivered volume and verification
percentages use `NUMERIC`/`Decimal`. Canonical persisted units are m³/h, m³,
kPa, seconds, mm, kW and kWh.
