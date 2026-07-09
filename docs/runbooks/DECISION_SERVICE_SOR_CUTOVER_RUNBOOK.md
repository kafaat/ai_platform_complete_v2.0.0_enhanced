# Decision-service System of Record Cutover Runbook

This runbook promotes `decision-service` from an honest non-authoritative mirror to the
System of Record for Sahool's decision/outcome/learning loop.

The cutover is intentionally gated. Do not demote sahool-platform until all checks below pass
in staging against a real Postgres database and a representative tenant dataset.

## Current safe mode

```text
DECISION_SERVICE_SOR_ENABLED=false
sahool-platform = temporary authoritative writer
decision-service = mirror / read-side candidate
```

## Promotion target

```text
DECISION_SERVICE_SOR_ENABLED=true
decision-service = authoritative writer
sahool-platform = orchestrator/BFF and compatibility facade
```

## Prerequisites

1. Deploy the decision-service image that includes:
   - `services/decision-service/migration_runner.py`
   - `services/decision-service/backfill.py`
   - `services/decision-service/migrations/001_decision_sor.sql`
2. Confirm `DATABASE_URL` points to the intended decision database.
3. Confirm tenant RLS/session policy expectations for the target DB.
4. Keep sahool-platform authoritative until the final cutover flag is enabled.

## Migration check/apply

Dry check:

```bash
python services/decision-service/migration_runner.py --check
```

Apply migrations explicitly:

```bash
DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true \
python services/decision-service/migration_runner.py --apply
```

Verify after apply:

```bash
python services/decision-service/migration_runner.py --check
```

The migration runner uses:

```text
decision_service_schema_migrations
checksum drift detection
pg_advisory_xact_lock
```

## Backfill/count verification

Same database topology:

```bash
DATABASE_URL=postgres://... \
python services/decision-service/backfill.py --verify-counts
```

Split database topology:

```bash
PLATFORM_DATABASE_URL=postgres://platform... \
DECISION_DATABASE_URL=postgres://decision... \
python services/decision-service/backfill.py --verify-counts
```

This must show no decision-side count deficit before cutover.

## Staging cutover

Set the SoR flag only in staging first:

```bash
DECISION_SERVICE_SOR_ENABLED=true
```

Then verify:

```bash
curl /readyz
curl /contract
```

Expected:

```json
{"sor_enabled": true, "mode": "system-of-record"}
```

Run write tests for:

```text
POST /v1/decisions/record
POST /v1/dispatch/decisions
POST /v1/outcomes/record
POST /v1/recommendation-outcomes
POST /v1/learning/updates
GET  /v1/decisions
```

Required semantics:

```text
persisted=true only after real INSERT/UPDATE
outbox event emitted
untraceable learning update rejected
idempotency key prevents duplicate outcomes
```

## Rollback

If any cutover check fails:

```bash
DECISION_SERVICE_SOR_ENABLED=false
```

This returns decision-service to honest mirror mode. Do not drop tables during rollback. Keep
sahool-platform as the temporary Source of Record until the incident is closed.

## Final production cutover

Production cutover is allowed only after:

1. `migration_runner.py --check` passes.
2. `backfill.py --verify-counts` passes.
3. Staging write/read/outbox/idempotency tests pass.
4. Tenant isolation has been verified against real Postgres.
5. Observability dashboards show no write or outbox backlog errors.

Only then may the platform be changed from authoritative writer to orchestrator/BFF.

## Hard stop

do not demote sahool-platform until migration checks, backfill verification, staging write tests,
tenant isolation checks, and rollback rehearsal have all passed.
