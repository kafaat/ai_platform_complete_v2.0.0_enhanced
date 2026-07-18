# FII Safety Continuation — Boundary-aware Chemical Lineage

## Scope
Safety Stabilization only. No Workspace, general FieldObservation SoR, ML, Registry, new event-driven projection, or learning work was added.

## Changes

1. Chemical Lineage is now boundary-aware:
   - `draft`, `submit`, `approve`, `dispatch`, `execute`.
   - Draft creation requires field/season/diagnosis/evidence lineage but does not require prior human approval.
   - Approve/dispatch/execute boundaries require explicit human approval.
   - Pest escalation resume with `approval_status=approved` is evaluated as the execution boundary.
2. Legacy prescription safety:
   - `season_resolution_status='unresolved'` records are excluded from operational list responses by default.
   - Administrative inspection remains possible through `include_legacy=true`.
   - Unresolved prescriptions cannot be exported to a machine-facing Shapefile; export fails with `LEGACY_SEASON_UNRESOLVED`.
3. Compatibility:
   - Chemical Lineage remains in `audit` by default.
   - No production enforcement was enabled.
   - Existing prescription clients remain compatible.

## Verification

- Targeted tests: 22 passed.
- Python compile check: passed.
- Live PostgreSQL certification remains pending because the execution environment has no PostgreSQL/Docker and no `TEST_DATABASE_URL`.
- Ruff is unavailable in this execution environment; no claim is made that the Ruff gate ran here.

## Remaining gate

Do not switch `FII_CHEMICAL_LINEAGE_MODE` to `enforce` until:

- live PostgreSQL role/RLS matrix passes;
- audit violations are classified and below the approved threshold;
- false positives are repaired;
- rollback from enforce to audit is rehearsed in staging.
