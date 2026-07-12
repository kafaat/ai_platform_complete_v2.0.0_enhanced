# Agronomic Runtime Terminal Lineage Continuation

## Scope
This continuation closes the remaining agronomic cohort lineage gaps in rollback and terminal runtime receipts.

## Implemented
- Added migration `024_runtime_terminal_agronomic_lineage.sql`.
- Propagated agronomic cohorts and fingerprint into rollback commands and rollback receipts.
- Propagated agronomic cohorts and fingerprint into rollout receipts.
- Propagated agronomic cohorts and fingerprint into retraining dispatch receipts.
- Added PostgreSQL triggers that reject cohort substitution at each terminal boundary.
- Corrected active-state monitoring so the latest rollback transition is authoritative, rather than always selecting the latest activation receipt.
- Added `source_transition_type` (`activation` or `rollback`) to monitoring snapshots.
- Extended active-state projection with agronomic cohorts and transition provenance.
- Added CI gate and focused tests.

## Verification
- Python compileall: PASS
- Workflow YAML parse: PASS
- Eight agronomic/vegetation CI gates: PASS
- Decision agronomic tests: 16 passed, 1 skipped (PostgreSQL required)
- AgriAI tests: 10 passed
- Vegetation focused tests: 13 passed

## Remaining external certification
Migration 024 and its triggers still require execution against a real PostgreSQL environment. The skipped database test is not claimed as passed.
