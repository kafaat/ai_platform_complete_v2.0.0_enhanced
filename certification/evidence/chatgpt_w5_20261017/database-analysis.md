# Five database gaps — analysis and isolated PG16 witnesses only

Source base: `ec3927cef45a3da53aaa14950093e734ce8e072a`. Exact source file hashes
and line positions are in `source-locations.json`. Nothing under any
`migrations/` directory or any MANIFEST is modified. SQL below is a **proposal
in this document**, not an executable migration, authorization or rollout.

## Reproduction environment and evidence boundary

The local environment has no Docker/Podman/PostgreSQL service. A PostgreSQL
16.2 binary was obtained via `pgserver==0.1.4`, but startup was blocked when its
root launcher attempted to create an OS service user (`useradd`, exit 1).
No root-check patch or permission workaround was used. Thus local collection
is not represented as successful PG execution.

The existing `Decision 033 Restricted Role Proof (PG16)` CI job already starts
a disposable loopback PostgreSQL 16 instance and explicitly runs
`services/decision-service/tests/test_migration_034_pg16.py`. Four new cases
were added to that existing module; **no workflow file was edited**, avoiding
Claude's workflow ownership. The inherited fixture accepts only its exact
disposable loopback DSN, asserts PG16, creates a unique database and restricted
LOGIN role, authenticates that role afresh, and cleans up afterward.

```bash
# From services/decision-service, with the EXISTING disposable CI instance only:
DECISION_033_REQUIRE_PG16=1 \
DECISION_033_TEST_DATABASE_URL=postgresql://decision033_admin:disposable_test_only@127.0.0.1:5436/decision033_test \
pytest tests/test_migration_033_pg16.py tests/test_migration_034_pg16.py \
  -v -p no:cacheprovider --junitxml=decision-033-pg16.xml
```

The constant password above belongs solely to the pre-existing disposable
CI fixture. No production credential is read, printed or supplied. The CI
JUnit on the final PR SHA is the execution receipt. Before that run completes,
the new PG16 cases are **collected, execution pending**, not passing witnesses.

## CP997-05-EDGE-IDEMPOTENCY-GLOBAL-UNIQUE-VS-TENANT-LOOKUP-01

Sources: `migrations/v9_edge_idempotency.sql:10-12` and
`services/sahool-platform/api/routers/edge.py:43-78` (conflict target at `:51`).

Repro: `test_cp997_global_conflict_hides_other_tenant_row` applies the actual
v9 index SQL to a minimal table in the disposable database. Tenant A inserts
`shared-key`; restricted tenant B's matching `ON CONFLICT ... DO NOTHING`
returns no row, and the tenant-qualified lookup also finds nothing. The router
then maps this condition to 409. This test covers the database conflict/lookup
mechanism, not the HTTP/auth path or a full platform-MANIFEST installation.

Proposed new migration, after freeze release and coordinated writer update:

```sql
BEGIN;
LOCK TABLE public.edge_results IN SHARE ROW EXCLUSIVE MODE;
CREATE UNIQUE INDEX uq_edge_tenant_idempotency
  ON public.edge_results (tenant_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
DROP INDEX public.uq_edge_idempotency;
COMMIT;
```

The application conflict target must change to `(tenant_id, idempotency_key)`
with the same predicate in the same controlled rollout. Do not drop the global
index while an old writer still targets it: PostgreSQL will reject that writer
with no matching conflict constraint. A concurrent-index variant needs a
separate nontransactional rollout plan; the snippet above deliberately takes a
write lock and therefore needs a measured maintenance window.

Acceptance: same key across A/B gives two independent rows; repeated same-key
same-payload A produces one result; same-key changed payload is 409; concurrent
same-tenant retries commit one row; null keys preserve legacy behavior; restricted
roles cannot read/update the other tenant; upgrade/rollback and old-writer
compatibility must be measured. No implementation or migration is made here.

## TENANT-GUC-NAME-DIVERGES-ACROSS-POLICY-FAMILIES-01

Sources: `migrations/v9_rls_tenant_isolation.sql:26-29` uses
`app.current_tenant`; `migrations/v106_phase9_10_runtime_strengthening.sql:50-57`
uses `app.tenant_id`; `migrations/v161_soil_p1_products.sql:35` uses
`app.current_tenant_id`. `services/sahool-platform/api/phase_runtime_workers.py:47`
is an example of a writer compensating for divergent names.

Repro: `test_v161_wrong_guc_silently_returns_empty_rows` applies the actual v161
DDL/policies. The restricted connection sees zero rows when only the canonical
or legacy GUC is set, then exactly A's row when the v161 GUC is set. It never
uses an admin connection for the visibility assertion. This demonstrates one
actual policy family, not complete convergence of all policy families.

Proposed direction (owner approves canonical name and rollout sequence): retain
`app.current_tenant` as the candidate canonical context. Inventory every policy,
type and writer; make writer transaction scope consistent before moving each
policy family. Do not add permissive OR/COALESCE fallbacks accepting conflicting
tenant contexts. Missing, empty, malformed and mutually inconsistent context
must fail closed at the contract boundary.

Example replacement text for one v161 policy in a new migration:

```sql
ALTER POLICY tenant_isolation ON public.soil_sampling_plans
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), ''))
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), ''));
```

Apply reviewed, type-correct equivalents to all five v161 tables and the other
families only after complete inventory; preserve intentional global-row policy
semantics separately. Acceptance: all three families with canonical-only,
legacy-only, absent, empty, malformed and conflicting context; SELECT/INSERT/
UPDATE/DELETE with two restricted identities; no connection-pool/session leakage;
all named application/worker consumers; upgrade and rollback. A guard against
a fourth spelling is not evidence of migration completion.

## SECURITY-DEFINER-FUNCTIONS-OWNED-BY-SUPERUSER-WITH-PUBLIC-EXECUTE-01

Sources: `migrations/v86_calibration_evidence_trigger.sql:51-97` defines the
trigger definer without a local search path; `migrations/v88_field_owner_function.sql:25`
and `migrations/v158_soil_projection_observability.sql:29` already revoke PUBLIC.
Therefore the gap title must not be interpreted as “all nine functions are
PUBLIC-callable” or as proof of a production exploit.

Repro: `test_v86_definer_catalog_exposes_owner_acl_and_unset_path` compiles the
actual v86 function definition on PG16 under the disposable migration admin.
It reads `pg_proc`, `pg_roles`, expanded default ACL, EXECUTE and schema USAGE:
SECURITY DEFINER, superuser/BYPASSRLS owner, unset proconfig, PUBLIC EXECUTE.
It does not invoke the trigger or claim exploitability. A trigger function
cannot simply be invoked as an ordinary SQL function; effective triggering
rights and table contracts matter.

Before a fix, apply the **full platform MANIFEST** to a fresh PG16/PostGIS clone
and retain the following inventory (not completed by the reduced CI fixture):

```sql
SELECT p.oid::regprocedure, r.rolname, r.rolsuper, r.rolbypassrls,
       p.proconfig, p.proacl, n.nspname
FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner
JOIN pg_namespace n ON n.oid=p.pronamespace WHERE p.prosecdef;
-- Expand COALESCE(proacl, acldefault('f',proowner)); inspect explicit grants,
-- role memberships, schema USAGE/CREATE and database TEMP for each caller.
```

Proposed new migration text for **v86 only**, subject to consumer/RLS validation:

```sql
CREATE ROLE sahool_calibration_definer NOLOGIN NOSUPERUSER NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO sahool_calibration_definer;
GRANT SELECT, INSERT, UPDATE ON public.calibration_evidence
  TO sahool_calibration_definer;
ALTER FUNCTION public.fn_update_calibration_evidence()
  OWNER TO sahool_calibration_definer;
ALTER FUNCTION public.fn_update_calibration_evidence()
  SET search_path = pg_catalog, public, pg_temp;
REVOKE ALL ON FUNCTION public.fn_update_calibration_evidence() FROM PUBLIC;
```

This is an incomplete candidate until existing-role handling, explicit grants,
trigger dependencies, qualified body names and restricted-owner RLS behavior are
tested. Do not apply the same owner policy blindly to the field-owner resolver
or cross-tenant projection workers: they have deliberate capabilities that must
be preserved with explicitly reviewed access. Proposed acceptance: authorized
triggers still update only their expected tenant; unrelated callers cannot gain
write/read rights; temporary-schema and caller-search-path shadowing tests;
PUBLIC plus explicit ACL negatives; forced-RLS owner behavior; full-MANIFEST
upgrade/rollback. The full inventory and exploit assessment remain open.

## DECISION-033-LEGACY-POLICY-UNION-01

Sources: `services/decision-service/migrations/033_tenant_boundary_hardening.sql:14,28`,
`migrations/v122_rls_with_check_session_unification.sql`, existing
`services/decision-service/migrations/034_tenant_boundary_policy_composition.sql:9,20`,
and `services/decision-service/tests/test_migration_034_pg16.py:29`.

The source fix is **already on main**, not an unimplemented new migration.
Existing `test_034_closes_legacy_policy_union` reproduces acceptance under 033
plus the legacy permissive policy, then proves rejection after the actual 034
restrictive policy on both tables for nonowner and FORCE-RLS owner LOGIN roles.
Its existing rollback/scoped-runner cases remain part of the same PG16 CI job.

The reviewed migration plan is to apply the existing pinned 033/034 pair after
explicit operational authorization, not rewrite or duplicate historical SQL.
Its essential policy is:

```sql
CREATE POLICY decision_outbox_events_tenant_boundary_guard
ON decision_outbox_events AS RESTRICTIVE FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
-- The existing 034 file supplies the corresponding decision_reviews policy.
```

Remaining acceptance: restore-point proof, exact journal/checksum inspection,
committed staging application of the approved pair, and canonical-only,
legacy-only, missing and conflicting contexts under a restricted identity on
both tables. No SoR promotion or NATS publisher activation is implied. Staging
status here is not remeasured; the registry's historical observation is retained.

## MIGRATOR-SCRIPT-DEFAULT-ROLE-PASSWORDS-01

Sources: `migrations/apply_in_compose.sh:74-76` rejects absent/empty ingest,
app and jobs credentials; `:296` uses PASSWORD NULL for unset optional Odoo.
This source fix already landed in #1170. A new migration is **not needed to
remove defaults** and is not proposed. Credential rotation/remediation on a
real environment is a separate authorized operational plan, with no secrets
placed in migration source or evidence.

Local repro uses the actual shell script via
`tests_v9/test_apply_in_compose_fail_closed.py`: missing required credentials
fail before psql, read-only inspection does not require them, and missing Odoo
credentials produce the explicit no-password path. Together with the existing
SAM2 digest suite, 54 tests passed locally (raw log retained separately).
The new PG16 `test_pg16_password_null_disables_password_credentials` verifies
the same SQL PASSWORD NULL semantics on the disposable role; it does not claim
that the entire production migrator has been executed or that Railway values
are correct.

Remaining acceptance: owner-controlled secret presence check without revealing
values, reject absent/empty configuration before all DB mutations, authorized
authentication smoke for provisioned roles, no public/default credential reuse,
and a deployment receipt showing the guarded revision ran. Production and
staging were not contacted. The gap remains open for operational proof.
