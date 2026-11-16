-- v280: purge the synthetic RANDOM() NDVI seed from ndvi_timeseries (plan item W1-21,
-- findings remote-2 / data-7).
-- ════════════════════════════════════════════════════════════════════════
-- The fault: init_v8.sql seeds ndvi_timeseries with 30 days of RANDOM() values for the demo
-- fields (field_01..field_08) and no tenant_id. The table has no live writer; NL-GIS
-- (ndvi_drop) and decision confidence read it, so the only NDVI they could ever see was this
-- invented series. Those readers now go through raster-service (api.raster_service_client.
-- latest_index_points), and this migration removes the invented rows.
--
-- Scope: rows with tenant_id IS NULL only. Every seeded row has tenant_id NULL (the seed never
-- sets it), and such a row belongs to no tenant: RLS hides it from every tenant connection.
-- Rows that carry a tenant_id are never touched.
--
-- Idempotent: a second run deletes nothing. On a database where init_v8.sql is re-applied
-- (the manifest is applied twice by design), init_v8 re-inserts the seed and this file, later in
-- the manifest, deletes it again. Table owner and writer: sahool-platform
-- (docs/architecture/db_ownership.yml).

BEGIN;
SET LOCAL lock_timeout = '15s';

DELETE FROM ndvi_timeseries WHERE tenant_id IS NULL;

COMMENT ON TABLE ndvi_timeseries IS
    'Legacy NDVI series (init_v8). No live writer and no reader: the platform reads NDVI from '
    'raster-service. v280 removed the tenant-less RANDOM() seed rows (W1-21).';

COMMIT;
