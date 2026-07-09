# Decision-service System of Record Migration

This package adds the first safe cutover foundation for making `decision-service` the
System of Record for the decision/outcome/learning loop.

## Current default

`decision-service` remains an honest mirror unless both flags are present:

```bash
DECISION_SERVICE_SOR_ENABLED=true
DATABASE_URL=postgres://...
```

Without those, write endpoints return `persisted=false` and `authoritative=false`.
This protects Sahool from the historical `persisted:true` stub failure.

## Added SoR foundation

- `services/decision-service/persistence.py`
- `services/decision-service/migrations/001_decision_sor.sql`
- `services/sahool-platform/tests/test_p0_decision_sor_migration_guard.py`

The migration creates:

- `decision_record`
- `dispatch_decisions`
- `outcome_record`
- `recommendation_outcomes`
- `online_learning_updates`
- `decision_outbox_events`

## Cutover sequence

1. Apply the migration to the decision-service database.
2. Backfill closed-loop rows from `sahool-platform`.
3. Run real Postgres tenant/isolation tests.
4. Enable `DECISION_SERVICE_SOR_ENABLED=true` only in staging.
5. Compare dual-read outputs.
6. Promote platform routes to orchestrator/BFF mode.
7. Remove direct platform writes only after the above is green.

## Non-negotiable guards

- No `persisted=true` without a real database write.
- No learning update without traceability.
- No outcome write without decision lineage.
- No platform demotion before decision-service real DB tests are green.
