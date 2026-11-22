# Decision-service SoR: staging cutover runbook (W2-01)

**Owner decision, 2026-11-16:** move the decision System of Record to `decision-service` on
**staging now**. Production follows later, as a separate decision. This runbook is the operator
sequence for staging only. It does not authorize production cutover, platform demotion
(`SAHOOL_DECISION_WRITE_MODE=decision_service_sor`) or the platform-write REVOKE: all three need
`DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED=true`, which is never set on staging.

**Deadline:** the authority exceptions that track `DECISION-SOR-CUTOVER-WIRING-01` were due to
expire on **2026-11-30** (`AUTHORITY-EXCEPTIONS-CO-EXPIRE-ON-2026-11-30-01`). On 2026-11-22 the owner extended
them to **2026-12-31** (SHR-01, `sahool-brain/decisions/ledger.md`). A staging cutover does not close
that gap. Before 2026-12-31 the owner either closes the gap or records a new decision.

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
| 4 | Gates, SoR flag, outbox proof (staging only) | decision-service environment | 4b `missing_gates` = outbox only; 4c outbox row; 4d `review_available: true`, `gates_complete: true` |
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

Recipe (run once as the database admin; adapt role names, set real passwords out of band).
`sahool_app` stands for the platform app role: replace it with the real name before running.

```sql
CREATE ROLE decision_schema_owner LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE decision_service_app  LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE decision_sor_auditor  LOGIN NOSUPERUSER BYPASSRLS   NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT CREATE ON SCHEMA public TO decision_schema_owner;
GRANT USAGE ON SCHEMA public TO decision_service_app, decision_sor_auditor;
-- ALTER TABLE takes one table per statement. Changing the owner also moves every sequence the
-- table owns (recommendation_outcomes_outcome_id_seq) and drops the old owner from the ACL of
-- the table and of those sequences.
ALTER TABLE decision_record          OWNER TO decision_schema_owner;
ALTER TABLE dispatch_decisions       OWNER TO decision_schema_owner;
ALTER TABLE outcome_record           OWNER TO decision_schema_owner;
ALTER TABLE recommendation_outcomes  OWNER TO decision_schema_owner;
ALTER TABLE online_learning_updates  OWNER TO decision_schema_owner;
ALTER FUNCTION sahool_chain_correlation_root() OWNER TO decision_schema_owner;      -- check the
ALTER FUNCTION sahool_chain_correlation_immutable() OWNER TO decision_schema_owner; -- signatures
-- Default privileges cover objects the migrator creates later, never the existing ones.
ALTER DEFAULT PRIVILEGES FOR ROLE decision_schema_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO decision_service_app;
ALTER DEFAULT PRIVILEGES FOR ROLE decision_schema_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO decision_service_app;
ALTER DEFAULT PRIVILEGES FOR ROLE decision_schema_owner IN SCHEMA public
  GRANT SELECT ON TABLES TO decision_sor_auditor;
-- Existing tables: explicit grants.
GRANT SELECT, INSERT, UPDATE, DELETE ON decision_record, dispatch_decisions, outcome_record,
      recommendation_outcomes, online_learning_updates TO decision_service_app;
-- Interim, while the platform is still the writer (staging): if the platform app role owned
-- these tables, the owner change above removed it from their ACL. Re-grant its DML. When it
-- was not the owner this is a no-op. The production REVOKE (platform_sor_revoke.py) removes it.
GRANT SELECT, INSERT, UPDATE, DELETE ON decision_record, dispatch_decisions, outcome_record,
      recommendation_outcomes, online_learning_updates TO sahool_app;
-- Existing sequences owned by the five tables moved with them: both inserting roles need
-- USAGE (nextval of the BIGSERIAL default) and SELECT on each one.
DO $grant_sor_sequences$
DECLARE seq regclass;
BEGIN
  FOR seq IN
    SELECT d.objid::regclass FROM pg_depend d JOIN pg_class s ON s.oid = d.objid
    WHERE d.classid = 'pg_class'::regclass AND d.refclassid = 'pg_class'::regclass
      AND s.relkind = 'S' AND d.deptype IN ('a', 'i')
      AND d.refobjid = ANY (ARRAY['decision_record', 'dispatch_decisions', 'outcome_record',
                                  'recommendation_outcomes', 'online_learning_updates']::regclass[])
  LOOP
    EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO decision_service_app, sahool_app', seq);
    RAISE NOTICE 'granted USAGE, SELECT on sequence %', seq;
  END LOOP;
END
$grant_sor_sequences$;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO decision_sor_auditor;
```

Check the two function signatures with `\df sahool_chain_correlation_*` before the `ALTER
FUNCTION`. The `DO` block prints one `NOTICE` per sequence; on the current schema that is
`recommendation_outcomes_outcome_id_seq` only.

**What the owner change does to existing grants.** `ALTER TABLE ... OWNER TO` keeps the grants of
roles other than the old owner, but the old owner itself leaves the ACL of the table and of the
sequences the table owns. Where the platform app role created the five tables (the usual case: it
applied the platform manifest), it loses every privilege on them, and `decision_service_app`
never had any on the moved sequence. Without the explicit grants above, both inserts fail:
`permission denied for table recommendation_outcomes` for the platform and `permission denied for
sequence recommendation_outcomes_outcome_id_seq` for decision-service. The interim platform grants
keep the platform writing the five tables while it is still the writer. In the split-database
topology the decision database has its own owner; only the migrator/app/auditor split applies
there, and the `sahool_app` lines are dropped.

**Verified on PG16, verbatim.** `tests_v9/test_decision_sor_staging_recipe_live_pg.py` extracts
this block from the file and runs it unchanged on a live PostgreSQL in a throwaway database:
the five tables (with the `BIGSERIAL` on `recommendation_outcomes`) and the two trigger functions
are first created by a NOSUPERUSER, NOBYPASSRLS `sahool_app`, the recipe then runs in one
transaction (any error stops it), and an `INSERT` into each table, through the sequence default,
must succeed as `decision_service_app` and as `sahool_app`. The same test against the previous
recipe (table grants for `decision_service_app` only) fails with exactly the two errors above.
The block was also run through `psql -X -v ON_ERROR_STOP=1 -f` on PostgreSQL 16.15 after the same
setup: rc 0, one `NOTICE` for `recommendation_outcomes_outcome_id_seq`, then
`INSERT INTO recommendation_outcomes (tenant_id) ... RETURNING outcome_id` returned 1 as
`decision_service_app` and 2 as `sahool_app`. An earlier draft used a multi-table `ALTER TABLE`,
which PostgreSQL rejects.

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

**`DECISION-SOR-PRE-CUTOVER-ROLE-CERTIFICATION` stays open on a `FAILED` result.** The operator
does not close it by reading the JSON. It closes only when one of these holds:

1. the run on staging over the two real connections exits 0 with `classification: PASSED`, and
   `role_certification.json` is kept as evidence; or
2. the owner records a decision in `sahool-brain/decisions/ledger.md` that accepts the
   sequence-privilege path, naming that JSON (exit 2, sole blocker
   `platform_sequence_privilege_present:recommendation_outcomes_outcome_id_seq`,
   `role_separation_confirmed: true`).

Until then the operator records the run as evidence of role separation and leaves the gap open.
Production repeats the run later.

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

Every gate is set only after its proof exists. The outbox gate cannot be proven before the flag:
`persistence.sor_enabled()` persists nothing until `DECISION_SERVICE_SOR_ENABLED` is set, and
`readiness_from_env()` needs every gate, outbox included, for `can_enable_sor`. So the flag comes
before the outbox gate, in a short window that `/readyz` reports openly. Never set the outbox
gate before step 4c has shown the row.

**4a. Five gates with proof in hand.** On the staging decision-service:

| Variable | Set after |
|---|---|
| `DATABASE_URL` | the `decision_service_app` connection |
| `DECISION_SERVICE_MIGRATIONS_VERIFIED=true` | step 2 output and a clean `--check` |
| `DECISION_SERVICE_BACKFILL_VERIFIED=true` | step 3, both verifiers `ok: True` |
| `DECISION_SERVICE_TENANT_ISOLATION_VERIFIED=true` | the decision-service real-Postgres tenant suites, green against this schema level |
| `DECISION_SERVICE_STAGING_CUTOVER_APPROVED=true` | the owner decision of 2026-11-16 |

Leave `DECISION_SERVICE_OUTBOX_VERIFIED` unset.

**4b. The flag, with the outbox gate still missing.** Set `DECISION_SERVICE_SOR_ENABLED=true` and
redeploy. `/readyz` must show `sor_capability.mode: persisted`,
`persisted_without_verified_gates: true`, `missing_gates: ["DECISION_SERVICE_OUTBOX_VERIFIED"]`
(nothing else), `cutover_mode: sor-requested-but-not-ready` and `can_enable_sor: false`. Any other
missing gate: set the flag back to `false` and return to 4a. The platform is still the writer
(`SAHOOL_DECISION_WRITE_MODE=shadow`), so this window affects staging decision-service only.

**4c. One persisted write and its outbox row.** On a staging test tenant, make one write that
must persist, for example `POST /v1/decisions/record` (bearer and `X-Tenant-Id`). The answer must
carry `persisted: true`. Then, as the auditor, confirm the row:

```sql
SELECT event_type, aggregate_type, status
FROM decision_outbox_events
WHERE aggregate_id = '<decision_id from the answer>';
-- expect exactly one row: DECISION_RECORDED, decision_record, pending
```

The row stays `pending`: no relay reads `decision_outbox_events` or sets `published_at`, so the
event is recorded and not delivered to any consumer (F-D01). Do not wait for it to change state.
`/readyz` reports this openly in its `outbox` block (`relay_implemented: false`,
`delivery: not_delivered`, the pending count and the age of the oldest pending row). Under the
restricted runtime role (`decision_service_app`, NOBYPASSRLS) that block reads
`measured: false` (`row_level_security_hides_other_tenants`) rather than a false `0`: the count
needs a role that sees every tenant. As the auditor (BYPASSRLS, read-only):
`SELECT count(*), now() - min(created_at) FROM decision_outbox_events WHERE status = 'pending';`

No row, or `persisted` not true: set the flag back to `false` (section R) and stop. The outbox gate
stays unset.

**4d. The outbox gate.** Only now set `DECISION_SERVICE_OUTBOX_VERIFIED=true` and redeploy.
The gate means "pending row recorded, not delivered" (`/v1/cutover/readiness` and
`sor_capability` carry it as `outbox_gate_proves`, with `outbox_relay_implemented: false`). It
does not prove that any consumer received the event.
`/readyz` must show `gates_complete: true`, `persisted_without_verified_gates: false` and
`can_enable_sor: true` (the full list is below). Step 5's probe passes only from here on.

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
| `review_available` | `persisted` **and** `/readyz` ready. Conservative: the review queue itself returns 503 only in mirror mode (it checks the SoR flag alone), so `true` means the queue is served, while `false` with `persisted: true` means the service is not ready and the queue may still answer or fail on the database. Clients show or hide review on this field |
| `gates`, `missing_gates`, `gates_complete` | the six verification gates, by variable name |
| `persisted_without_verified_gates` | true when the flag was set before the gates: an operator shortcut made visible |
| `cutover_mode`, `can_enable_sor`, `can_demote_platform` | as in `/v1/cutover/readiness` |
| `migration_level` | `code_head`, `applied_head`, `pending_count`, `current`, `known_count` |

Expected after step 4d: `mode: persisted`, `review_available: true`, `gates_complete: true`,
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

- **`DECISION-SOR-PRE-CUTOVER-ROLE-CERTIFICATION`**: closed only by step 1 on staging over the two
  real connections with `classification: PASSED` and the JSON kept, or by an owner decision in the
  ledger that accepts the sequence-privilege path for that JSON. A `FAILED` run alone leaves it
  open. Production repeats it before any REVOKE.
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
