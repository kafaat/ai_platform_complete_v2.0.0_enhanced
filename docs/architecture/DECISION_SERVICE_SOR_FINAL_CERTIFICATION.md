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

### WX-10.7 review transition

The reviewer/policy transition is authoritative only under a deployed SoR. Certification must
confirm the review layer: migration `002` applied (review columns + append-only `decision_reviews`),
the review parity/quarantine verifier (`backfill.py --verify-review`) reports an empty quarantine,
and a post-cutover proof exercises approve, reject, and a cross-tenant lookup that is denied without
an oracle. Ambiguous backfilled candidates are fail-closed un-reviewable, never mis-approved.

## Final certification checklist

1. migration runner check passed (001 + 002);
2. backfill verification passed;
3. WX-10.7 review parity/quarantine (`backfill.py --verify-review`) empty and clean;
4. staging probe passed (including a review approve/reject rehearsal);
5. read-side comparison passed;
6. `/v1/cutover/readiness` returns `can_demote_platform=true` and `/readyz` reports `db_reachable`/`migrations_current`;
7. production promotion preflight passed;
8. rollback dry-run reviewed (retains the append-only `decision_reviews` audit);
9. post-cutover review proof: create candidate → approve; separate candidate → reject; cross-tenant review denied;
10. platform write smoke test retained until cutover is complete.


rollback is non-destructive.
