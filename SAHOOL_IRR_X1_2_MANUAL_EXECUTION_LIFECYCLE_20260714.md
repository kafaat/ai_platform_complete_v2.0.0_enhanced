# SAHOOL IRR-X1.2 Manual Execution Lifecycle

Implemented a governed vendor-neutral manual irrigation execution return path:

Recommended → Approved → Started → Stopped → Confirmed → Verified → Reconciled

Key guarantees:
- recommendation is not execution;
- recommendation-only mode cannot start execution;
- estimated execution remains non-ledger-eligible;
- measured meter/flow evidence is required for measured ledger eligibility;
- illegal state skips fail closed;
- event history is append-only;
- tenant RLS and idempotency keys are enforced in v187;
- no vendor adapter or automatic dispatch is introduced.

New API routes:
- POST /api/v1/irrigation/engineering/manual-executions
- POST /api/v1/irrigation/engineering/manual-executions/{execution_id}/transition
- POST /api/v1/irrigation/engineering/manual-executions/{execution_id}/confirm

Validation executed:
- Python compilation: PASS
- IRR-X1 guard: PASS
- IRR-X1.1 guard: PASS
- IRR-X1.2 guard: PASS
- Migration manifest: PASS (193 migrations, through v187)
- Focused tests: 5 passed

Not claimed:
- v187 was not applied to a live PostgreSQL instance;
- no field hardware or controller was exercised;
- verified/reconciled API automation and live water-ledger transaction remain a later increment;
- no frontend farmer workflow was mounted in this increment.
