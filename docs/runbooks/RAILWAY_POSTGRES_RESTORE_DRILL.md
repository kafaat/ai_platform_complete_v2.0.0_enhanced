# Railway production PostgreSQL: restore drill (owner-run)

Gap: `PRODUCTION-ENVIRONMENT-ALL-DEPLOYMENTS-REMOVED-SINCE-20261005-01`, item 2. No backup of the
production database has been proven restorable. The owner decided on 2026-10-25 to read the
Railway Usage and Billing pages first (item 1). This page prepares item 2. It is a drill on a
**disposable copy**. It changes nothing in production and runs no migration.

General procedure, physical bases and PITR: [`POSTGRES_RECOVERY.md`](POSTGRES_RECOVERY.md). This
page covers only the Railway case: one logical export restored into a throwaway local database.

## Never do during the drill

- Never use Railway's "Restore" action on the production volume: it replaces the live data.
- Never run the migrator, `alembic`, or any SQL that writes. Never set `SAHOOL_MIGRATE_APPLY`.
- Never restart, resize or redeploy `sahool-postgres` or any production service.
- Never paste the connection string into chat, a commit, a log or an issue.

## 1. Export (read-only on production)

From a trusted machine with `psql`/`pg_dump` at the server's major version (15):

```bash
# The URL comes from the Railway dashboard (service sahool-postgres → Connect), never from chat.
export PGURL='…'                     # read it into the shell only
pg_dump --format=custom --no-owner --no-privileges --file sahool_prod_$(date -u +%Y%m%dT%H%MZ).dump "$PGURL"
sha256sum sahool_prod_*.dump > sahool_prod.sha256
unset PGURL
```

`pg_dump` takes a consistent snapshot in one read-only transaction. It needs no lock beyond
`ACCESS SHARE`, and no write.

## 2. Restore into a disposable database

```bash
docker run --rm -d --name sahool-restore-drill -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=sahool \
  -p 127.0.0.1:55432:5432 postgis/postgis:15-3.4
sleep 15
# RLS policies and grants name roles: create every role the export references, without login.
pg_restore --list sahool_prod_*.dump | grep -oE '(POLICY|ACL).*' | head   # inspect which roles appear
PGPASSWORD=drill psql -h 127.0.0.1 -p 55432 -U postgres -d sahool -c 'CREATE ROLE sahool_user NOLOGIN;'   # repeat per role
PGHOST=127.0.0.1 PGPORT=55432 PGUSER=postgres PGPASSWORD=drill PGDATABASE=sahool \
  bash scripts/restore_postgres.sh sahool_prod_*.dump --force
```

If the restore stops on `role "…" does not exist`, create that role the same way and rerun:
the stop is `--exit-on-error` doing its job, not a failed drill.

`--force` is used only because the target is the new, empty drill container. `pg_restore
--exit-on-error` (inside the script) fails on the first SQL error rather than reporting success.

## 3. What proves the drill

Record the following in the gap row, with the dump's sha256:

| Check | Command (on the drill database) |
| --- | --- |
| Restore finished without error | exit code 0 of step 2 |
| Schema version matches production | `SELECT * FROM alembic_version;` (read only) |
| Row counts of the core tables | `SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY 1;` compared with the same query on production |
| RLS still enabled | `SELECT relname FROM pg_class WHERE relrowsecurity AND relforcerowsecurity;` |
| PostGIS present | `SELECT postgis_full_version();` |
| Time to restore | wall clock of step 2 (the measured RTO for a logical restore) |

Then `docker rm -f sahool-restore-drill` and delete the dump unless the owner keeps it encrypted.

## What this does not prove

- A logical dump is not point-in-time recovery: the data is as of the export only.
- Railway's own volume backups are a separate mechanism; this drill does not test them.
