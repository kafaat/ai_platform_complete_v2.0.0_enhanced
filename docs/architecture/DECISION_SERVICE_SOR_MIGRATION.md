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
- `services/decision-service/migrations/002_decision_review.sql` (WX-10.7 review layer)
- `services/sahool-platform/tests/test_p0_decision_sor_migration_guard.py`

`001_decision_sor.sql` creates:

- `decision_record`
- `dispatch_decisions`
- `outcome_record`
- `recommendation_outcomes`
- `online_learning_updates`
- `decision_outbox_events`

`002_decision_review.sql` (WX-10.7) is additive + idempotent and adds:

- `decision_record.review_state` (CHECK `pending_approval|approved|rejected`),
  `decision_record.candidate_lineage_id`, `decision_record.updated_at`;
- the append-only `decision_reviews` audit table (DB trigger blocks UPDATE/DELETE);
- a one-time backfill of existing candidates to `review_state='pending_approval'`.

Both migrations are applied by the custom runner (`migration_runner.py --apply`), never at
application startup, via the observable pre-deploy step `scripts/deploy/decision_service_migrate.sh`.

## WX-10.7 review backfill and quarantine

`002` backfills every `stage='candidate'` row to `review_state='pending_approval'` and lifts
`candidate_lineage_id` out of `decision_value` jsonb. The backfill is deterministic and
idempotent, but a candidate whose evidence lacks a `candidate_lineage_id` is left with a NULL
lineage. That is **fail-closed un-reviewable** (the atomic transition keys on
`candidate_lineage_id = $` and NULL never matches a supplied lineage), NOT a silent mis-approval.

Before flipping ownership, run the read-only parity/quarantine verifier so ambiguous candidates
are resolved deliberately instead of guessed:

```bash
DATABASE_URL=postgres://... python services/decision-service/backfill.py --verify-review
```

It quarantines (never mutates) any candidate with a NULL/empty `candidate_lineage_id`, an
un-backfilled/invalid `review_state`, or an evidence `status` that disagrees with the candidate
stage. A non-empty quarantine blocks cutover until an operator resolves each row.

## Cutover sequence

1. Apply the migrations to the decision-service database (`scripts/deploy/decision_service_migrate.sh`).
2. Backfill closed-loop rows from `sahool-platform`; verify counts and the WX-10.7 review parity
   (`backfill.py --verify-counts` and `backfill.py --verify-review`).
3. Run real Postgres tenant/isolation tests (including the WX-10.7 review transition tests).
4. Enable `DECISION_SERVICE_SOR_ENABLED=true` only in staging.
5. Compare dual-read outputs.
6. Promote platform routes to orchestrator/BFF mode.
7. Remove direct platform writes only after the above is green.

## Non-negotiable guards

- No `persisted=true` without a real database write.
- No learning update without traceability.
- No outcome write without decision lineage.
- No platform demotion before decision-service real DB tests are green.
