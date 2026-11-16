-- v280 rollback: nothing to restore.
-- Rollback script, not listed in MANIFEST.txt (forward-only manifest, as for every *.down.sql).
-- v280 deleted the tenant-less rows of ndvi_timeseries, which were the RANDOM() demo seed of
-- init_v8.sql (no tenant, no live writer, hidden from every tenant by RLS). That synthetic data
-- is deliberately NOT restored: re-inserting random NDVI would put back exactly the invented
-- observations W1-21 removed. Rows with a tenant_id were never touched by v280, so there is
-- nothing else to bring back. Only the table comment v280 set is cleared. Idempotent.
BEGIN;
SET LOCAL lock_timeout = '15s';
COMMENT ON TABLE ndvi_timeseries IS NULL;
COMMIT;
