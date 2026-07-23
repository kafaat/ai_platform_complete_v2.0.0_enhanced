# Programmatic closure review — merged baseline fbe6048

## Scope

This increment uses `fbe6048` as the baseline, preserves
`DECISION-CENTER-UNIFY-01`, and restores or completes programmatic work found
in the prior-session lineage. It does not claim a
production cutover, external-provider delivery, model certification, or live
equipment execution.

## Implemented in this increment

- Restored the simple farmer book on the existing Farm Ledger:
  expense/income, cash/credit, supplier/customer, cashbox/debt settlement,
  field/season/document linkage, monthly and per-hectare totals, CSV/PDF, and
  offline idempotency.
- Registered its migration, table ownership, backend coverage, frontend route,
  navigation, permissions, and route budget.
- Upgraded Agronomic Replay source truth:
  canonical historical-weather fallback and structured
  `available|empty|unavailable` status with count/source/quality per track.
- Added a deterministic, leakage-aware exporter from eligible historical
  simulation-run evidence to the existing SIM-GOLDEN contract. Tenant IDs are
  never exported; farm identifiers are salted pseudonyms.
- Preserved the fail-closed Crop Twin preview-only and Field Intelligence
  decision-center gates from `fbe6048`.
- Enforced AC-1 automatically in production even when its rollout flag is
  omitted or explicitly false.

## Verification evidence

- Unified targeted suite: `65 passed, 4 skipped`. This includes the
  `fbe6048` Decision Center gates plus farmer book, historical-season bridge,
  Replay, SIM-GOLDEN, operational truth, route budget, DB ownership, migration
  completeness and runner synchronization.
- The four skipped tests require a live PostgreSQL test DSN.
- Frontend `npm run typecheck`: passed.
- Migration manifest: 217 migrations, passed.
- S0–S12 baseline gate: passed.
- Production honesty, AC-1 context and decision-lineage gates: passed.
- Generated inventory: 32 services and 1,094 routes.
- Release bundle validation: 4,817 checksums verified.

## Live certification still required

- S1: Decision SoR cutover, permission revocation and parity on the target DB.
- S4: closed-loop E2E against deployed workers/adapters and measured outcomes.
- S6: actual provider credentials and delivery receipts.
- S7: PCSE/WOFOST golden seasons and regional calibration.
- S9: signed ONNX artifact and device evaluation.
- S12: staging/production certification, rollback rehearsal and operator sign-off.

These are runtime/evidence activities. Marking them complete from source code
alone would violate the production-honesty contract.
