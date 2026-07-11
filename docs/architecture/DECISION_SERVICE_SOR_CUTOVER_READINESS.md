# Decision-service SoR Cutover Readiness Contract

This contract extends the P0 strangler foundation. It does not perform production cutover.
It makes the cutover mechanically auditable.

## Non-negotiable invariants

- `decision-service` must not return `persisted=true` unless `DECISION_SERVICE_SOR_ENABLED=true` and `DATABASE_URL` is set.
- sahool-platform remains the temporary authoritative writer until staging proves decision-service persistence.
- Schema changes are explicit release actions through `migration_runner.py`, never application import side effects.
- Backfill/count verification is required before promotion.
- Learning updates require lineage: `source_type/source_id`, `recommendation_id`, `decision_id`, or `evidence_snapshot_id`.
- Outcome writes must be idempotent by `(tenant_id, idempotency_key)` when an idempotency key is present.
- Outbox rows are emitted for every authoritative decision-service write.

## Cutover states

| State | Flag | Writer | Allowed response |
|---|---|---|---|
| Mirror | `DECISION_SERVICE_SOR_ENABLED=false` | `sahool-platform` | `persisted=false`, `authoritative=false` |
| Staging SoR | `DECISION_SERVICE_SOR_ENABLED=true` | `decision-service` | `persisted=true`, `authoritative=true` after DB write |
| Production SoR | `DECISION_SERVICE_SOR_ENABLED=true` | `decision-service` | same as staging, with platform as BFF |

## WX-10.7 review layer

- The reviewer/policy transition (`pending_approval → approved|rejected`) is carried by the
  dedicated `decision_record.review_state`/`candidate_lineage_id` columns and the append-only
  `decision_reviews` audit table (migration `002_decision_review.sql`).
- Under mirror mode the review endpoint fails closed (503) — a state transition is never mirrored.
- Ambiguous backfilled candidates (NULL `candidate_lineage_id`) are fail-closed un-reviewable, never
  mis-approved; they must be surfaced and resolved before the ownership flip.

## Required gates

- Static CI: `scripts/ci/decision_sor_cutover_readiness_gate.py`
- Migration check: `python services/decision-service/migration_runner.py --check`
- Migration apply (observable pre-deploy step): `scripts/deploy/decision_service_migrate.sh`
  (`DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true python services/decision-service/migration_runner.py --apply`)
- Backfill verification: `python services/decision-service/backfill.py --verify-counts`
- WX-10.7 review parity/quarantine: `python services/decision-service/backfill.py --verify-review`
- DB readiness: decision-service `/readyz` reports `db_reachable` and `migrations_current` when `DATABASE_URL` is set
- Runtime tests: real Postgres tenant isolation and outbox/idempotency checks, plus the review transition tests
