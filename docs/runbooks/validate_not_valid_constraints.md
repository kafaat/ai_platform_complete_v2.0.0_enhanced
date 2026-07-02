# Runbook — Validating the deferred (`NOT VALID`) CHECK constraints

Migrations **v127**, **v130**, and **v132** added CHECK constraints as `NOT VALID`.
This is deliberate: `NOT VALID` lets the DDL take only a brief `ACCESS EXCLUSIVE` lock
to attach the constraint metadata **without scanning existing rows**, avoiding a heavy
lock/long scan on large tables at migration time. Consequently the constraints are
enforced for **new and updated rows only** until an operator explicitly runs
`ALTER TABLE ... VALIDATE CONSTRAINT ...`.

`VALIDATE CONSTRAINT` scans the whole table once (under a `SHARE UPDATE EXCLUSIVE`
lock — it does **not** block reads/writes, but it is I/O heavy) and **fails hard** if
any existing row violates the predicate. Therefore we never run a *blind* validate:
we report violations first, clean them up, then validate in a monitored window.

## Tracked constraints

| Migration | Table | Constraint | CHECK predicate (verbatim) |
|-----------|-------|-----------|----------------------------|
| v132 | `field_state` | `chk_field_state_version` | `version >= 1` |
| v127 | `recommendation_outcomes` | `chk_reco_outcomes_tenant_not_null` | `tenant_id IS NOT NULL` |
| v127 | `recommendation_outcomes` | `chk_reco_outcomes_predicted_yield_nonnegative` | `predicted_yield_t_ha IS NULL OR predicted_yield_t_ha >= 0` |
| v127 | `recommendation_outcomes` | `chk_reco_outcomes_actual_yield_nonnegative` | `actual_yield_t_ha IS NULL OR actual_yield_t_ha >= 0` |
| v130 | `soil_lab_tests` | `chk_soil_lab_ph_range` | `ph IS NULL OR (ph >= 0 AND ph <= 14)` |
| v130 | `soil_lab_tests` | `chk_soil_lab_nonneg` | conjunction: each analyte `IS NULL OR >= 0`, `organic_matter_pct` in `0..100`, `sample_depth_cm >= 0`, `result_version >= 1` |
| v130 | `soil_lab_tests` | `chk_soil_lab_sample_method` | `sample_method IS NULL OR sample_method IN ('composite','grid','zone')` |

A row violates a CHECK when the predicate is **FALSE** (NULL passes). The report and
guard count `WHERE NOT (<predicate>)`, which is exactly the set of rows that would make
`VALIDATE CONSTRAINT` fail.

## The 5-step procedure

### 1. (done) Add the constraint as `NOT VALID`
Already shipped in v127/v130/v132. Do **not** add a new `vXXX_*.sql` that runs
`VALIDATE CONSTRAINT` — step 4 is operator-run, not a migration.

### 2. Run the violation report
```bash
TEST_DATABASE_URL=postgresql://user:pass@host:5432/db \
  python scripts/migrations/report_not_valid_constraint_violations.py
```
Reads `TEST_DATABASE_URL` (preferred) or `DATABASE_URL`. Exit codes: `0` clean,
`1` violations found (per-constraint counts + sample `ctid`s printed), `2` no DB / could
not connect. Point it at the target environment (staging first, then prod replica/prod).

### 3. Clean up / backfill the offending rows
Only if step 2 reports violations. Scope each fix to the failing predicate, e.g.:

```sql
-- field_state: a bad projection wrote version 0 / negative. Backfill to the floor.
UPDATE field_state SET version = 1 WHERE NOT (version >= 1);

-- recommendation_outcomes: tenant scope must be present (investigate provenance first;
-- do NOT invent a tenant — quarantine/delete orphans per data-retention policy).
--   SELECT * FROM recommendation_outcomes WHERE tenant_id IS NULL;   -- triage
-- negative yields are data-entry/units errors:
UPDATE recommendation_outcomes SET predicted_yield_t_ha = NULL
  WHERE NOT (predicted_yield_t_ha IS NULL OR predicted_yield_t_ha >= 0);
UPDATE recommendation_outcomes SET actual_yield_t_ha = NULL
  WHERE NOT (actual_yield_t_ha IS NULL OR actual_yield_t_ha >= 0);

-- soil_lab_tests: out-of-range analytes / bad sample_method — re-extract from the raw
-- JSONB `result`, or NULL the derived column, per lab QA. Never clamp silently without
-- an agronomy sign-off.
```
Re-run step 2 until it exits `0`.

### 4. `VALIDATE CONSTRAINT` in a monitored window
Only after step 2 is clean. Run each statement individually, watching lock/I-O and
replication lag. `VALIDATE CONSTRAINT` does not block reads/writes but is a full scan.

```sql
ALTER TABLE field_state             VALIDATE CONSTRAINT chk_field_state_version;
ALTER TABLE recommendation_outcomes VALIDATE CONSTRAINT chk_reco_outcomes_tenant_not_null;
ALTER TABLE recommendation_outcomes VALIDATE CONSTRAINT chk_reco_outcomes_predicted_yield_nonnegative;
ALTER TABLE recommendation_outcomes VALIDATE CONSTRAINT chk_reco_outcomes_actual_yield_nonnegative;
ALTER TABLE soil_lab_tests          VALIDATE CONSTRAINT chk_soil_lab_ph_range;
ALTER TABLE soil_lab_tests          VALIDATE CONSTRAINT chk_soil_lab_nonneg;
ALTER TABLE soil_lab_tests          VALIDATE CONSTRAINT chk_soil_lab_sample_method;
```
These are **documentation** — run them by hand (or via a controlled ops job), never as
an auto-applied migration. After validation, `convalidated` flips to `true`:
```sql
SELECT conname, convalidated FROM pg_constraint
 WHERE conname LIKE 'chk_field_state_%'
    OR conname LIKE 'chk_reco_outcomes_%'
    OR conname LIKE 'chk_soil_lab_%';
```

### 5. Re-report + CI guard
Re-run step 2 (should be `0`). The CI guard
`tests_v9/test_not_valid_constraint_no_new_violations_guard.py` keeps this durable:
- **unit**: the `NOT VALID` constraints still exist verbatim in their migrations and no
  blind `VALIDATE CONSTRAINT` was added to a migration file.
- **integration** (`pytest -m integration`, needs `TEST_DATABASE_URL`): zero violating
  rows on the migrated test DB, so a future dirty seed/schema regression fails CI.

## Rollback / safety notes
- Nothing here drops data by default; step 3 edits are the only mutations and are
  reviewed per constraint.
- If a `VALIDATE CONSTRAINT` fails, the constraint simply stays `NOT VALID` (no data
  change) — return to step 2/3.
- Keep the constraints `NOT VALID` (still enforcing new rows) rather than dropping them
  if validation must be deferred; the guard forbids silently dropping them.
