# SAHOOL Farmland — Phase 2

Shared working reference for every party executing Phase 2 (Claude Code, Codex, GIS, advisor,
platform/UI, lab and hospital), so all of them start from the same inventory instead of
re-deriving it.

- [`PHASE2_INVENTORY_main_35c305c2.md`](PHASE2_INVENTORY_main_35c305c2.md) — read-only inventory
  of what exists and what is missing per domain, measured against `main` at `35c305c2`
  (2026-11-25). It is a starting point, not proof of absence: re-check `main` before building
  anything it lists as missing, and reuse or strengthen what exists rather than duplicating it.

## Corrections to the inventory (owner, 2026-11-25)

- **EPANET** already exists in the agricultural calculator (a separate repository) together with
  its earlier test evidence. The inventory's "Missing: EPANET/WNTR" refers to this platform
  repository only. The Wave 2 work is to verify that it can be reused and linked to the
  platform, **not** to build a second hydraulic engine.
- **Wells:** a pumping-test result alone is not evidence of sustainable abstraction from the
  aquifer.

## Proposed execution split (owner, 2026-11-25)

A coordination proposal, not a statement that every team has started.

| Wave | Scope | Owner |
|---|---|---|
| 1 | Standards & compliance, soil and land evaluation | Claude Code |
| 2 | Water, irrigation, drainage, energy | Codex |
| 3 | Levelling, spatial evaluation, costs | GIS team |
| 4 | GeoRAG and the unified decision source | Advisor team |
| 5 | Inspection, assets, maintenance | Platform & UI team |
| 6 | Review, integration, verification | Lab & hospital |

Deliveries are cumulative ZIPs: **ZIP 01** = Wave 1 + Wave 2, **ZIP 02** = Wave 3 + Wave 4,
**ZIP 03** = Wave 5 + Wave 6. Each carries the real code, per-domain patches, internal tests and
their results, and apply/rollback instructions. Initial ZIPs do not wait for external
acceptance, but the acceptance gates still apply before any merge or deploy. None of it is
applied directly to production.

## Technical notes that bind every wave (owner, 2026-11-25)

- Standards: keep a standard's validity separate from its local adoption; results are
  `pass` / `fail` / `not_evaluated` / `not_applicable`.
- Gypsum and reclamation: compute from CEC, exchangeable sodium, treatment depth, bulk density
  and gypsum purity; never invent missing lab values.
- Land classification: show the limiting factors and their source; no final class when core
  evidence is missing.
- Energy: link pump curves to hourly solar simulation, water demand, tanks and operating cost.
- Crop suitability: unify the four implementations gradually, with old-vs-new compatibility
  tests.
