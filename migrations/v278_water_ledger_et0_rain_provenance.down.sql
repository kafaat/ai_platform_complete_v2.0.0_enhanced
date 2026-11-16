-- v278 rollback: removes the ET0/rain provenance columns from water_ledger (W0-10).
-- Rollback script, not listed in MANIFEST.txt (forward-only manifest, as for every *.down.sql).
-- Data note: dropping the columns discards each row's ET0 method, quality, weather snapshot, rain
-- source and TAW/RAW; et0_mm and rain_mm stay. Roll back the platform code (the W0-10 change to
-- phase_runtime_workers.py and routers/water_ledger.py) first, so no writer still names the
-- columns. Idempotent (IF EXISTS).
BEGIN;
SET LOCAL lock_timeout = '15s';
ALTER TABLE water_ledger DROP CONSTRAINT IF EXISTS water_ledger_root_zone_check;
ALTER TABLE water_ledger DROP CONSTRAINT IF EXISTS water_ledger_rain_source_check;
ALTER TABLE water_ledger DROP CONSTRAINT IF EXISTS water_ledger_et0_quality_check;
ALTER TABLE water_ledger DROP CONSTRAINT IF EXISTS water_ledger_et0_method_check;
ALTER TABLE water_ledger DROP COLUMN IF EXISTS raw_mm;
ALTER TABLE water_ledger DROP COLUMN IF EXISTS taw_mm;
ALTER TABLE water_ledger DROP COLUMN IF EXISTS rain_source;
ALTER TABLE water_ledger DROP COLUMN IF EXISTS weather_snapshot_id;
ALTER TABLE water_ledger DROP COLUMN IF EXISTS et0_quality;
ALTER TABLE water_ledger DROP COLUMN IF EXISTS et0_method;
COMMIT;
