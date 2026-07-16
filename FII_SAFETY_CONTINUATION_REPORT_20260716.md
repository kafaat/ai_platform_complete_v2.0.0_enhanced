# FII Safety Continuation Report — 2026-07-16

## Scope respected

Only the approved Safety Stabilization program was extended. No Workspace, general FieldObservation SoR, ML, registry, new event-driven FII projection, or learning subsystem was added.

## Completed in this continuation

### RLS batch 2 — chemical decision/execution chain

Fresh-install migrations and a corrective migration now enforce fail-closed tenant write isolation for:

- `recommendations`
- `decision_record`
- `work_orders`
- `actuator_command_dedup`
- `outcome_record`
- `lineage_link`

Corrective migration: `migrations/v194_fii_chemical_chain_rls_fail_closed.sql`.

The policy invariant is:

```sql
USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
```

### Runtime role boundary hardening

`migrations/apply_in_compose.sh` no longer grants runtime schema `CREATE` to `sahool_app` by default. It explicitly revokes it.

A temporary legacy exception is available only through:

```text
APP_ALLOW_SCHEMA_CREATE=true
```

It is default-off and emits an audit warning. It is not acceptable for production certification.

Added:

- `scripts/security/fii_rls_role_gate.py`
- `scripts/security/fii_rls_live_role_audit.sql`
- `tests/security/test_fii_rls_role_gate.py`

The live audit checks that `sahool_app`:

- is not superuser/BYPASSRLS/CREATEDB/CREATEROLE,
- has no `CREATE` on `public`,
- is not a member of `sahool_schema_owner`,
- owns no tenant table.

### Ratchets and migration registration

- FII RLS static gate scope expanded to the chemical chain migrations.
- `v194` registered in `migrations/MANIFEST.txt` and `scripts_v9/run_migrations.sql`.
- Fresh-install migrations were corrected as well as deployed-schema correction, preventing reintroduction on new environments.

## Validation

- Migration static validation: all migrations through `v194` passed.
- Targeted Safety tests: `11 passed, 1 skipped`.
- Skipped item: live PostgreSQL RLS matrix because Docker/PostgreSQL and a live test URL are unavailable in this environment.
- Bash syntax validation passed for migration/bootstrap scripts.

## Remaining before Increment 1 production closure

1. Run `tests_v9/test_fii_rls_write_fail_closed_postgres.py` against real PostgreSQL.
2. Run `scripts/security/fii_rls_live_role_audit.sql` using the production-equivalent roles.
3. Verify connection-pool tenant reset under real asyncpg pooling.
4. Run `production_validation_gate.sh` and staging probe.
5. Inventory and migrate any runtime service that still depends on `APP_ALLOW_SCHEMA_CREATE=true`; production must keep it false.

## Chemical Lineage status

Chemical Lineage remains `audit` by default. It was deliberately not switched to `enforce`, because real audit metrics and staging proof are still required.
