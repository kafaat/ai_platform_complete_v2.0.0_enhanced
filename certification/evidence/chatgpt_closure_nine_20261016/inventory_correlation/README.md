# Inventory and correlation closure work — 2026-10-16

Base: `6e8cc0f9952c037550ae1644919f88c475dd89a7`.

## Implemented

- Inventory SELECT-policy admission now validates the actual canonical tenant equality,
  rather than accepting any SQL expression mentioning the expected GUC. Six red cases
  included `OR true`, a restrictive `AND false`, wrong-column and inverted comparisons.
- Platform v235 and Decision 036 introduce stored UUID correlation on the actual chains
  documented in `docs/architecture/decision_chain_correlation.md`. Database triggers cover
  every existing insert path; legacy rows stay NULL, child identities come from explicit
  same-tenant parents, and row identity/correlation cannot be changed later.
- Decision authoritative responses and platform decision/dispatch/ledger projections expose
  the stored UUID or explicit NULL. The trace is not an authorization or a new evidence hash.
- Complete native PG16 fixtures are ready for the existing disposable CI database: full
  Decision migration runner plus actual writers, and real inventory SQL/RLS with a
  documented minimal projection schema. No live/production acceptance is claimed here.

## Measured locally

| Evidence | Result | Scope |
|---|---|---|
| Inventory policy witnesses on base | 6 failed, 1 control passed | Reproduces admission defect |
| Inventory suite after fix | 32 passed | Driver-isolated unit suite |
| Correlation result projection on base / fixed | 14 failed / 14 passed | Representation boundary only |
| Existing Decision unit cases | 95 passed | 318 other cases deselected |
| Existing platform endpoint/list/persistence cases | 26 passed | No database or physical action |
| PostgreSQL-WASM SQL contract | 20 passed | PGlite 0.3.14 / PostgreSQL 17.5; minimal relational fixture |
| Native PG16 acceptance | 2 tests prepared, locally skipped | Binary available, OS prevents required unprivileged server launch |

`correlation_sql_acceptance.mjs` is independently repeatable with an installed PGlite
module path; `correlation-pglite.json` is the measured receipt. It is not native PG16 and
must never substitute for that CI job. `validation.json` records local log hashes.

## Required before closure claims

1. Parent review and new byte-scoped GATE-01 adjudication for the frozen manifest/ownership
   changes and actual migration-runner alias; the global gate stays CLOSED. No prior U07
   grant is reused. This worktree does not issue its own grant.
2. Native PostgreSQL CI execution on the final integration head. The historic 033/034
   policy-only witnesses must remain isolated from new tracing triggers; final-schema
   acceptance is a separate witness, not a relaxed error-code expectation.
3. Authorized tenant census in the actual environment with the inventory's bounded,
   read-only, repeatable-read contract. Unknown providers and truncation remain visible.
   Local rows, an empty fixture and a staging-only read cannot establish production census.
4. Owner-controlled schema rollout and read-only trace acceptance, preserving authoritative
   root IDs during any future ownership cutover. Independently written mirror databases
   are not claimed to share the authoritative trace automatically.

No production writes, migration application, deployment, brain state edit, push or merge
was performed by this agent. Runtime census evidence gathered by the coordinator must be
attached separately and must identify its exact environment and scope.

## Compatibility and public projection review follow-up

The initial platform child trigger broke historically permitted direct ledger and
physical irrigation inserts whose parent is absent. The corrected v235 leaves
those rows explicitly NULL only when the caller supplied no correlation; a supplied
non-NULL identity is refused. The service's approved chain remains strict.
`platform_migration_acceptance.mjs` applies the actual v66/v67/v68/v78/v178 table
migrations and v235 twice: eight cases pass, including old checks, orphan writes,
foreign-parent invisibility and no forged identity. The subset needs an explicit
fixture RLS helper for v66/v68; it is not the full PostGIS platform or native PG16.

Decision root creation/replay, list and both review queues now return stored
correlation. List reads bind canonical tenant context transaction-locally, so
restricted-role native assertions do not rely on admin visibility. Four actual
HTTP root tests fail on base and pass after the projection change (mocked
persistence, real authentication middleware). Native036 tests exercise the real
writers, lists and tenant-negative cases; they remain unexecuted locally.
The two delivery/outcome fixtures now seed actual parent chains rather than orphan
request references; strict service triggers are unchanged.

Final measured local scope: 50 targeted passes, two native skips; 99 Decision
unit passes; 20 relational SQL contract cases and eight platform compatibility
cases in PGlite. No deployment, native PG16 acceptance, actual runtime inventory,
or full integration preflight is claimed by this agent receipt.

## Current-role inventory policy admission follow-up

The collector now checks policy applicability to the connected role (PUBLIC,
direct role, and inherited membership) and requires a permissive SELECT policy
for every source. A canonical predicate attached only to a different role, or
only restrictive policies, previously allowed a misleading empty snapshot. Five
new witnesses fail on `c4e04746`; the inventory suite passes 37 cases after the
fix. Six actual catalog-query cases pass in PGlite, including missing policy and
role inheritance. The native PG16 fixture now exercises role exclusion and
restrictive-only refusal; it has not been executed locally.

The refreshed `runtime-inventory-query-manifest.json` is generated from the
collector's exact SQL. `policy_role_acceptance.mjs` takes manifest path, installed
PGlite module path, and output path. Combined local targeted verification is
55 passed, 2 native database skips; this is not a production census.
