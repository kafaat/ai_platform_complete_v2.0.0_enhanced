# Decision-service SoR Final Certification

This document defines the final certification layer for promoting decision-service to System of Record.

## Certification principle

promotion is not a single flag. A production cutover requires verified migrations, verified backfill, tenant isolation, outbox verification, staging approval, production approval, read-side comparison, and a rollback plan.

## Added controls

### read-side comparison

`services/decision-service/read_side_compare.py` performs read-only checks across sahool-platform and decision-service. It verifies migration/backfill state, the cutover readiness endpoint, and basic platform/decision health before promotion.

### Production promotion preflight

`services/decision-service/production_promotion.py` verifies all production flags and `/v1/cutover/readiness` before operators set `SAHOOL_DECISION_WRITE_MODE=decision_service_sor`.

### Rollback

`services/decision-service/rollback.py` provides a non-destructive rollback path. Rollback is non-destructive: decision-service tables are retained for forensic comparison while sahool-platform is restored as Source of Record.

## Final certification checklist

1. migration runner check passed;
2. backfill verification passed;
3. staging probe passed;
4. read-side comparison passed;
5. `/v1/cutover/readiness` returns `can_demote_platform=true`;
6. production promotion preflight passed;
7. rollback dry-run reviewed;
8. platform write smoke test retained until cutover is complete.


rollback is non-destructive.
