# Decision-service SoR Production Promotion Runbook

This runbook is the final operator path after staging probes pass. It does **not** turn production cutover into a single flag.

## 0. Required prior evidence

Before promotion, collect evidence for:

1. migration check and applied schema checksum;
2. backfill count verification;
3. tenant isolation verification;
4. outbox verification;
5. staging probe success;
6. read-side comparison success.

## 0.5 WX-10.7 review parity / quarantine

Apply migrations through the explicit, observable pre-deploy step (never at startup):

```bash
DATABASE_URL=postgres://... \
DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true \
scripts/deploy/decision_service_migrate.sh
```

> **Before this step — certify DB role separation (read-only, zero risk):**
> `services/decision-service/decision_sor_role_certify.py` with both connection URLs. A shared role
> yields `role_separation_confirmed=false`, which blocks the later REVOKE outright. Details in
> [`DECISION_SOR_CUTOVER.md`](DECISION_SOR_CUTOVER.md).

This applies **every** migration under `services/decision-service/migrations/` (`001…`, 31 files at
the time of writing — the set grows, so measure with
`ls services/decision-service/migrations/*.sql | wc -l` and never hand-pick a subset), re-runs
`--check` clean, and runs the read-only review parity/quarantine
verifier. Do not proceed while the quarantine is non-empty — an operator must resolve each ambiguous
candidate (a NULL `candidate_lineage_id` is fail-closed un-reviewable, never mis-approved), rather
than the migration guessing:

```bash
DATABASE_URL=postgres://... python services/decision-service/backfill.py --verify-review
```

## 1. read-side comparison

Run dry-run first:

```bash
python services/decision-service/read_side_compare.py
```

Run live read-only comparison only after approval:

```bash
SAHOOL_ENV=production \
DECISION_SERVICE_READ_COMPARE_APPROVED=true \
DECISION_SERVICE_READ_COMPARE_ALLOW_LIVE=true \
DECISION_SERVICE_READ_COMPARE_ALLOW_PRODUCTION=true \
python services/decision-service/read_side_compare.py --live
```

This step performs read-only checks. It must not create decisions, outcomes, or learning rows.

## 2. production promotion preflight

Run dry-run first:

```bash
python services/decision-service/production_promotion.py
```

Run live preflight only when the release manager has approved promotion:

```bash
SAHOOL_ENV=production \
DATABASE_URL=postgres://... \
DECISION_SERVICE_SOR_ENABLED=true \
DECISION_SERVICE_MIGRATIONS_VERIFIED=true \
DECISION_SERVICE_BACKFILL_VERIFIED=true \
DECISION_SERVICE_TENANT_ISOLATION_VERIFIED=true \
DECISION_SERVICE_OUTBOX_VERIFIED=true \
DECISION_SERVICE_STAGING_CUTOVER_APPROVED=true \
DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED=true \
DECISION_SERVICE_PRODUCTION_PROMOTION_APPROVED=true \
DECISION_SERVICE_PRODUCTION_PROMOTION_ALLOW_LIVE=true \
python services/decision-service/production_promotion.py --live
```

Promotion is allowed only when `/v1/cutover/readiness` returns `can_demote_platform=true`.

## 3. Runtime switch

After live preflight passes, switch runtime mode deliberately:

```bash
SAHOOL_DECISION_WRITE_MODE=decision_service_sor
```

Keep monitoring outbox, decision writes, outcome writes, and learning update lineage.

### 3.1 post-cutover review proof

Immediately after the switch, prove the WX-10.7 review transition against the live SoR:

1. create a candidate → `authoritative=true`, `persisted=true`, `review_state=pending_approval`;
2. approve it → `approved`, exactly one `decision_reviews` row, one outbox row;
3. reject a separate candidate → `rejected`;
4. cross-tenant lookup/review → denied or `not_found` without an oracle;
5. confirm no dual authoritative write (platform mirror stays best-effort, never authoritative).

Also confirm `/readyz` reports `db_reachable=true` and `migrations_current=true`.

## 4. rollback plan

Rollback is non-destructive:

```bash
python services/decision-service/rollback.py
```

Live rollback approval:

```bash
SAHOOL_ENV=production \
DECISION_SERVICE_ROLLBACK_APPROVED=true \
DECISION_SERVICE_ROLLBACK_ALLOW_LIVE=true \
python services/decision-service/rollback.py --live
```

Rollback order:

1. set `DECISION_SERVICE_SOR_ENABLED=false`;
2. set `SAHOOL_DECISION_WRITE_MODE=platform_sor`;
3. unset `DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED`;
4. verify platform decision writes;
5. do not delete decision-service tables during rollback;
6. retain the append-only `decision_reviews` audit and the `review_state`/`candidate_lineage_id`
   columns untouched (delete no review rows, reverse no completed transition); new reviews fail
   closed 503 in mirror mode;
7. run read-side comparison again;
8. return to shadow mode only after platform write smoke passes.

