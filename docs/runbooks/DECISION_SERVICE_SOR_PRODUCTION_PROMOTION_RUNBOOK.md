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
6. run read-side comparison again;
7. return to shadow mode only after platform write smoke passes.

