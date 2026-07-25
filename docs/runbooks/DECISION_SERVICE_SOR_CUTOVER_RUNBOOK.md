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

## Pre-cutover role certification (MANDATORY precursor to the REVOKE)

The DB-level REVOKE below is meaningful only if the platform and decision-service connect as
**different** Postgres roles. The repo does not fix this: the platform defaults to `sahool_app`, but
`DECISION_SERVICE_DATABASE_URL` is empty by default and its role is operator-supplied at cutover.
**Certify the live topology first** — this tool is read-only (it never runs GRANT/REVOKE), it only
prints the live privilege matrix:

```bash
DECISION_SOR_PLATFORM_URL=postgres://sahool_app...      \
DECISION_SOR_SERVICE_URL=postgres://decision_service... \
python services/decision-service/decision_sor_role_certify.py
```

Read the output and confirm, before any REVOKE:

- `role_separation_confirmed: true` — `current_user` differs between the two connections;
- both roles are `rolsuper: false`, `rolbypassrls: false`;
- neither app role **owns** the five SoR tables (owner keeps privileges even after REVOKE — the
  robust target is `table owner = decision_schema_owner` NOLOGIN, `sahool_app` = SELECT-only,
  `decision_service_app` = DML; this three-role model is a **recommendation**, to be turned into an
  ADR only if certification shows it is needed, not before);
- no sequence USAGE or SECURITY DEFINER function leaves the platform role an indirect write path;
- the platform role cannot `SET ROLE` to a stronger role (empty `memberships_can_set_role_to`).

**If `role_separation_confirmed` is false** (both connections resolve to the same role), do NOT run
the REVOKE — it would strip writes from both services. Instead: create `decision_service_app`, move
the decision-service connection to it, prove decision-service works on the new role, and only then
proceed to the REVOKE below.

## DB-level revocation of platform writes (same-DB topology only)

After the platform is demoted (`SAHOOL_DECISION_WRITE_MODE=decision_service_sor`,
`DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED=true`), close the dual-write window **at the
database** — not only in Python. This strips `INSERT/UPDATE/DELETE` from the platform role on the
five platform-owned SoR tables (`decision_record`, `dispatch_decisions`, `outcome_record`,
`recommendation_outcomes`, `online_learning_updates`) while **retaining `SELECT`** (the platform
stays a read-side BFF). The decision-service-owned `decision_outbox_events` is deliberately not
touched.

```bash
# Admin URL = a role that OWNS the SoR tables (or superuser) — NOT the platform app role.
DECISION_SOR_ADMIN_DATABASE_URL=postgres://owner...  \
DECISION_SOR_PLATFORM_ROLE=sahool_app                \
DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED=true    \
DECISION_SOR_ALLOW_PLATFORM_REVOKE=true              \
scripts/deploy/decision_sor_platform_revoke.sh revoke
```

This is a one-shot cutover step, **not** a migration (it lives outside
`services/decision-service/migrations/`, which run on every schema deploy — a REVOKE there would
strip platform writes before demotion and break the pre-cutover contract). It is a **no-op in the
split-DB topology** (the platform has no grant on the decision database) and simply need not be
run there. The rollback (`decision_sor_platform_revoke.sh rollback`, gated by
`DECISION_SERVICE_ROLLBACK_APPROVED=true`) is the exact inverse — it re-grants the writes.

After the revoke, verify the pre/post `has_table_privilege` state printed by the tool: every write
privilege on the five tables is `false` for the platform role, `SELECT` remains `true`.

## Hard stop

do not demote sahool-platform until migration checks, backfill verification, staging write tests,
tenant isolation checks, and rollback rehearsal have all passed.
