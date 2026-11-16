# Decision-service SoR: staging cutover runbook (W2-01)

**Owner decision, 2026-11-16:** move the decision System of Record to `decision-service` on
**staging now**. Production follows later, as a separate decision. This runbook is the operator
sequence for staging only. It does not authorize production cutover, platform demotion
(`SAHOOL_DECISION_WRITE_MODE=decision_service_sor`) or the platform-write REVOKE: all three need
`DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED=true`, which is never set on staging.

**Deadline:** the authority exceptions that track `DECISION-SOR-CUTOVER-WIRING-01` expire on
**2026-11-30** (`AUTHORITY-EXCEPTIONS-CO-EXPIRE-ON-2026-11-30-01`). A staging cutover does not
close that gap. Before that date the owner either closes the gap or records a new decision.

Every live step needs credentials the repository does not hold. The operator runs them. Pass
connection strings and tokens as environment variables in the execution shell; never paste them
into a chat, a ticket or this repository.

Related runbooks: [`DECISION_SERVICE_SOR_CUTOVER_RUNBOOK.md`](DECISION_SERVICE_SOR_CUTOVER_RUNBOOK.md)
(general cutover), [`DECISION_SOR_CUTOVER.md`](DECISION_SOR_CUTOVER.md) (Arabic, staging to
production), [`DECISION_SERVICE_SOR_STAGING_PROBE_RUNBOOK.md`](DECISION_SERVICE_SOR_STAGING_PROBE_RUNBOOK.md)
and [`DECISION_SERVICE_SOR_PRODUCTION_PROMOTION_RUNBOOK.md`](DECISION_SERVICE_SOR_PRODUCTION_PROMOTION_RUNBOOK.md).

## Sequence at a glance

| # | Step | Tool | Must show |
|---|---|---|---|
| 0 | Role topology | SQL as the database admin | four distinct roles (below) |
| 1 | Role certification | `decision_sor_role_certify.py` | `role_separation_confirmed: true` |
| 2 | Apply migrations | `scripts/deploy/decision_service_migrate.sh` | `decision_service_migrate_ok` |
| 3 | Backfill verification | `backfill.py --verify-counts`, `--verify-review` | `ok: True`, empty quarantine |
| 4 | Gates + SoR flag (staging only) | decision-service environment | `/readyz` `sor_capability.review_available: true` |
| 5 | Probe and review queue | `staging_probe.py --live`, review queue | probe `ok: true`, queue 200 |
| R | Rollback | `rollback.py --live`, flag off | `/readyz` `mode: mirror`, queue 503 |

## 0. Role topology

The tools assume four roles. In the same-database topology (platform and decision-service on one
Postgres) this is what the local rehearsal proved works:

| Role | Attributes | Used by | Privileges |
|---|---|---|---|
| `decision_schema_owner` | LOGIN, NOSUPERUSER, NOBYPASSRLS | `decision_service_migrate.sh` only | owns the decision tables |
| platform app role (e.g. `sahool_app`) | NOSUPERUSER, NOBYPASSRLS | sahool-platform | its existing grants |
| `decision_service_app` | NOSUPERUSER, NOBYPASSRLS | decision-service `DATABASE_URL` | DML on decision-owned tables |
| `decision_sor_auditor` | NOSUPERUSER, **BYPASSRLS**, read-only | backfill verifiers | SELECT only |

Why each one is needed (measured, not assumed):

- The DML-only app role cannot apply DDL: `migrate.sh` as that role stops with
  `permission denied for schema public`.
- Neither app role may own the five SoR tables: the certification blocks `app_role_owns_table`.
- In the same-database topology the platform migrations create the five SoR tables and the
  functions `sahool_chain_correlation_root` and `sahool_chain_correlation_immutable` (owner: the
  role that applied the platform manifest). Migration `036` replaces those two functions, so the
  migrator must own them too. Without that, `--apply` fails with
  `must be owner of function sahool_chain_correlation_root`, then `..._immutable`, and rolls back.
- `backfill.py` reads with `row_security=off`. Under an RLS-bound role PostgreSQL refuses
  (`query would be affected by row-level security policy for table "decision_record"`), which is
  intended: the verifier must never count a tenant-filtered subset. It therefore needs a
  BYPASSRLS read-only auditor.

Recipe (run once as the database admin; adapt role names, set real passwords out of band):

```sql
CREATE ROLE decision_schema_owner LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE decision_service_app  LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE decision_sor_auditor  LOGIN NOSUPERUSER BYPASSRLS   NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT CREATE ON SCHEMA public TO decision_schema_owner;
GRANT USAGE ON SCHEMA public TO decision_service_app, decision_sor_auditor;
ALTER TABLE decision_record, dispatch_decisions, outcome_record,
            recommendation_outcomes, online_learning_updates OWNER TO decision_schema_owner;
ALTER FUNCTION sahool_chain_correlation_root() OWNER TO decision_schema_owner;      -- check the
ALTER FUNCTION sahool_chain_correlation_immutable() OWNER TO decision_schema_owner; -- signatures
ALTER DEFAULT PRIVILEGES FOR ROLE decision_schema_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO decision_service_app;
ALTER DEFAULT PRIVILEGES FOR ROLE decision_schema_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO decision_service_app;
ALTER DEFAULT PRIVILEGES FOR ROLE decision_schema_owner IN SCHEMA public
  GRANT SELECT ON TABLES TO decision_sor_auditor;
GRANT SELECT, INSERT, UPDATE, DELETE ON decision_record, dispatch_decisions, outcome_record,
      recommendation_outcomes, online_learning_updates TO decision_service_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO decision_sor_auditor;
```

Check the two function signatures with `\df sahool_chain_correlation_*` before the `ALTER
FUNCTION`. Changing a table's owner keeps its existing grants, so the platform keeps writing the
five tables while it is still the writer. In the split-database topology the decision database
has its own owner; only the migrator/app/auditor split applies there.

## 1. Role certification (read-only)

```bash
DECISION_SOR_PLATFORM_URL="$PLATFORM_APP_URL" \
DECISION_SOR_SERVICE_URL="$DECISION_SERVICE_APP_URL" \
python services/decision-service/decision_sor_role_certify.py > role_certification.json
```

The tool never runs GRANT or REVOKE. Exit 0 = `classification: PASSED`, exit 2 = `FAILED`.

- `role_separation_confirmed: true` is required. `false` means both connections are one role: stop,
  create `decision_service_app`, move the decision-service connection to it, certify again.
- Neither role may be superuser or BYPASSRLS, neither may own a SoR table, and the platform role's
  membership closure must be empty.

**Known blocker on a live platform (owner decision needed).** The platform inserts
`recommendation_outcomes` through the `BIGSERIAL` default, so its role holds `USAGE` on
`recommendation_outcomes_outcome_id_seq`. The certification blocks any platform privilege on a
sequence owned by a SoR table (`platform_sequence_privilege_present:recommendation_outcomes_outcome_id_seq`),
and `platform_sor_revoke.py` revokes only table privileges, not sequence privileges. So while the
platform still writes, the certification reports `FAILED` with exactly this one blocker, and the
REVOKE would not remove it either. Reproduced in the local rehearsal. For staging this does not
block the SoR flag: no REVOKE happens on staging. Record the JSON as it is. If the only blocker is
this sequence and `role_separation_confirmed` is true, role separation is proven. Before any
production REVOKE the owner decides between extending the REVOKE to sequence privileges and
accepting this path.

**Closes `DECISION-SOR-PRE-CUTOVER-ROLE-CERTIFICATION`:** this run against staging over the two real
connections, with `role_certification.json` kept as evidence (the gap's closure condition). For
production the same run is repeated later.

## 2. Apply decision-service migrations

```bash
DATABASE_URL="$DECISION_SCHEMA_OWNER_URL" \
DECISION_SOR_AUDIT_DATABASE_URL="$DECISION_SOR_AUDITOR_URL" \
DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true \
bash scripts/deploy/decision_service_migrate.sh
```

- It stops if `DATABASE_URL` or the schema-change flag is missing.
- The pre-check exits 2 when migrations are pending (expected). Any other failure (no `asyncpg`,
  bad credentials, unreachable host) now stops the script before `--apply`. `PYTHON` selects the
  interpreter.
- The review verifier at the end uses `DECISION_SOR_AUDIT_DATABASE_URL`. Without it, it uses the
  owner connection, which is RLS-bound once FORCE RLS is on, and fails loudly.
- Re-running is safe: the journal and the advisory lock make `--apply` idempotent.
- Expect `decision_service_migrate_ok`. Then `migration_runner.py --check` as
  `decision_service_app` must print `'ok': True`.

## 3. Backfill verification

The verifiers only read. Same-database topology:

```bash
DATABASE_URL="$DECISION_SOR_AUDITOR_URL" python services/decision-service/backfill.py --verify-counts
DATABASE_URL="$DECISION_SOR_AUDITOR_URL" python services/decision-service/backfill.py --verify-review
```

Split-database topology: set `PLATFORM_DATABASE_URL` and `DECISION_DATABASE_URL` to auditor
connections on each side. In the same-database topology the five tables are physical platform
tables, so there is nothing to copy. `--verify-counts` proves the decision side sees every platform
row with identical shared columns. `--verify-review` must report `quarantine_count: 0`. A
quarantined candidate (for example, no `candidate_lineage_id`) is resolved by an operator, never
guessed.

## 4. Gates and the SoR flag (staging decision-service only)

Set each gate only after its proof exists:

| Variable | Set after |
|---|---|
| `DATABASE_URL` | the `decision_service_app` connection |
| `DECISION_SERVICE_MIGRATIONS_VERIFIED=true` | step 2 output and a clean `--check` |
| `DECISION_SERVICE_BACKFILL_VERIFIED=true` | step 3, both verifiers `ok: True` |
| `DECISION_SERVICE_TENANT_ISOLATION_VERIFIED=true` | the decision-service real-Postgres tenant suites, green against this schema level |
| `DECISION_SERVICE_OUTBOX_VERIFIED=true` | a persisted write in step 5 leaves its `decision_outbox_events` row |
| `DECISION_SERVICE_STAGING_CUTOVER_APPROVED=true` | the owner decision of 2026-11-16 |
| `DECISION_SERVICE_SOR_ENABLED=true` | all six above |

Also on staging: `DECISION_SERVICE_AUTH_TOKEN` (shared bearer) with
`DECISION_REQUIRE_AUTH_TOKEN=true`, and the platform stays the writer with
`SAHOOL_DECISION_WRITE_MODE=shadow`. Never set `DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED` here.

### The capability signal on `/readyz`

`GET /readyz` now carries `sor_capability` (contract `decision-sor-capability/v1`). It holds
booleans and identifiers only, never a connection string, token or error text. The gates come from
the same model as `/v1/cutover/readiness` (`services/decision-service/cutover.py`).

| Field | Meaning |
|---|---|
| `mode` | `persisted` when `DECISION_SERVICE_SOR_ENABLED` and `DATABASE_URL` are both set, else `mirror` |
| `review_available` | `persisted` **and** `/readyz` ready: the condition under which the review queue answers 200. Clients show or hide review on this field |
| `gates`, `missing_gates`, `gates_complete` | the six verification gates, by variable name |
| `persisted_without_verified_gates` | true when the flag was set before the gates: an operator shortcut made visible |
| `cutover_mode`, `can_enable_sor`, `can_demote_platform` | as in `/v1/cutover/readiness` |
| `migration_level` | `code_head`, `applied_head`, `pending_count`, `current`, `known_count` |

Expected after step 4: `mode: persisted`, `review_available: true`, `gates_complete: true`,
`cutover_mode: decision-service-sor-staging-shadow`, `can_enable_sor: true`,
`can_demote_platform: false`, `applied_head == code_head`, `pending_count: 0`.

## 5. Staging probe and review queue

```bash
SAHOOL_ENV=staging \
DECISION_SERVICE_STAGING_PROBE_APPROVED=true \
DECISION_SERVICE_STAGING_PROBE_ALLOW_LIVE=true \
DECISION_SERVICE_URL="$STAGING_DECISION_SERVICE_URL" \
DECISION_SERVICE_AUTH_TOKEN="$STAGING_DECISION_SERVICE_TOKEN" \
DATABASE_URL="$DECISION_SOR_AUDITOR_URL" \
python services/decision-service/staging_probe.py --live
```

- The probe runs `migration_runner.py --check`, `backfill.py --verify-counts` and
  `GET /v1/cutover/readiness`. Its readiness check passes only when `can_enable_sor` is true and
  `can_demote_platform` is false.
- It now sends the bearer from `DECISION_SERVICE_AUTH_TOKEN`. Before this change an authenticated
  staging service answered 401 and the probe could never pass. `DATABASE_URL` is the auditor,
  for the reason given in step 3.
- It refuses `SAHOOL_ENV=production`.

Then check the review queue, directly and through the platform BFF. Both must return 200
(`authoritative: true`):

```bash
curl -fsS -H "Authorization: Bearer $STAGING_DECISION_SERVICE_TOKEN" -H "X-Tenant-Id: $STAGING_TENANT" \
  "$STAGING_DECISION_SERVICE_URL/v1/decisions/review-queue"
curl -fsS -H "Authorization: Bearer $STAGING_USER_JWT" "$STAGING_PLATFORM_URL/api/v1/decisions/review-queue"
```

Plan acceptance for W2-01 also asks that vegetation evidence is accepted:
`POST /v1/evidence/vegetation-snapshots` returns `persisted: true` instead of 503.

## R. Rollback

```bash
SAHOOL_ENV=staging DECISION_SERVICE_ROLLBACK_APPROVED=true DECISION_SERVICE_ROLLBACK_ALLOW_LIVE=true \
python services/decision-service/rollback.py --live
```

1. Set `DECISION_SERVICE_SOR_ENABLED=false` on the staging decision-service and redeploy.
2. Keep `SAHOOL_DECISION_WRITE_MODE` at `shadow` or `platform_sor`. No REVOKE happened on staging,
   so there are no platform grants to restore.
3. Confirm `/readyz` shows `sor_capability.mode: mirror` and `review_available: false`, and the
   review queue answers 503 (fail closed, never an empty queue).
4. Delete nothing: decision tables, the `decision_reviews` audit and the review columns stay for
   forensics.
5. Unset the gate variables that no longer hold.

## Open gaps and what closes them

- **`DECISION-SOR-PRE-CUTOVER-ROLE-CERTIFICATION`**: closed by step 1 run on staging over the two
  real connections with the JSON kept. Production repeats it before any REVOKE.
- **`DECISION-SOR-CUTOVER-WIRING-01`**: **not** closed by a staging cutover. It closes when the
  production cutover applies the platform-write REVOKE on live PG16 (after
  `DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED`), with role separation certified and the sequence
  blocker above decided. Staging contributes the proof that the decision-service side works as the
  SoR.
- **`DEPLOYED-DECISION-SOR-PROMOTION`**: production promotion, a separate owner decision.

## Evidence: local PG16 rehearsal (2026-11-16)

Measured on a disposable PostgreSQL 16 + PostGIS with the full root `migrations/MANIFEST.txt`
applied first (the platform schema), then the four roles above (`decision_schema_owner`,
`sahool_app_stg`, `decision_service_stg`, `decision_sor_auditor`). Base `c720395a8` plus the change
that adds this runbook. No staging or production system was contacted.

| Step | Result |
|---|---|
| `migrate.sh` without the schema-change flag | exit 2, refused |
| `migrate.sh` with an interpreter lacking `asyncpg` | exit 1 at the pre-check, no apply (before the fix it printed "pending migrations present — expected" and carried on) |
| `migrate.sh` as the DML-only decision-service role | exit 1, `permission denied for schema public` |
| `migrate.sh` as the schema owner | needed ownership of the 5 SoR tables and the 2 `sahool_chain_correlation_*` functions, then `decision_service_migrate_ok`; 38 migrations, 49 tables owned |
| `migrate.sh` re-run | `decision_service_migrate_ok` (idempotent) |
| `migrate.sh` without the auditor URL | exit 1, row-level-security refusal (before the fix: `ok: True`, quarantine empty) |
| certification, two distinct roles | exit 0, `PASSED`, `role_separation_confirmed: true` |
| certification, platform holding `USAGE` on the outcome sequence | exit 2, sole blocker `platform_sequence_privilege_present:recommendation_outcomes_outcome_id_seq` |
| certification, one shared role / one connection | exit 2, `FAILED` |
| `--verify-review` with one lineage-less candidate, as the RLS-bound owner | before the fix exit 0 and `quarantine_count: 0` (silent miss); after the fix exit 1, refused |
| `--verify-review`, auditor | exit 2 with the candidate quarantined; exit 0 once resolved |
| `--verify-counts`: RLS-bound role / auditor | refused / `ok: True`, `same-db-verify` |
| `/readyz`, mirror | 200, `mode: mirror`, `review_available: false`; review queue 503 |
| `/readyz`, flag without gates | `persisted_without_verified_gates: true`, `cutover_mode: sor-requested-but-not-ready` |
| `/readyz`, flag + six gates | `mode: persisted`, `review_available: true`, `applied_head = code_head = 038_context_compositions.sql`, `pending_count: 0`; review queue 200; decision write `persisted: true` |
| `staging_probe.py --live` with the token | exit 0, all four steps ok (before the fix: readiness step 401) |
| `staging_probe.py --live`, `SAHOOL_ENV=production` | refused |
| rollback: `rollback.py --live`, flag off | exit 0; `mode: mirror`; review queue 503; the persisted row retained |

The rehearsal driver lives outside the repository (it starts a throwaway cluster). The defects it
found are fixed in this change and pinned by tests: `backfill.verify_review` (real-Postgres test in
`services/decision-service/tests/test_decision_sor_role_certify_pg.py`), the `migrate.sh`
pre-check and auditor URL, the probe bearer and the `/readyz` capability block
(`tests_v9/test_decision_sor_staging_cutover_prep.py`, `tests_v9/test_readiness_http_status.py`).
