-- v279: water_ledger records how each day's ET0 and rain were obtained (W0-10, weather-7).
-- ════════════════════════════════════════════════════════════════════════
-- The daily water-ledger worker (sahool-platform phase_runtime_workers.run_water_ledger_once)
-- wrote et0_mm and rain_mm with no provenance: ET0 was computed at sea level (the field's
-- elevation was not passed), a degraded Penman-Monteith counted as reference, and the day's
-- forecast rain was stored as if it had fallen. The worker now passes fields.elevation_m and
-- records, per row:
--   et0_method           weather-service ET0 method (fao56_penman_monteith | hargreaves_fallback)
--   et0_quality          weather-service quality_status (validated | degraded)
--   weather_snapshot_id  the ET0 product's weather_snapshot_id (the inputs the value came from)
--   rain_source          forecast (the day's forecast when the row is written) | observed (the
--                        weather-service archive, re-recorded once the archive has the day: the
--                        worker re-checks a window of recent forecast rows on every cycle, since
--                        the ERA5 archive lags about five days, and rebuilds the chain after them)
--   taw_mm, raw_mm       the root-zone TAW/RAW the row's depletion was computed against, so a
--                        later rebuild uses the row's own values, not today's texture or root zone
-- All six are NULL on rows written before v279 and on rows a person or the as-applied paths
-- write without an ET0/rain computation: NULL means "not declared", never "reference".
-- Owner and only writer: sahool-platform (docs/architecture/db_ownership.yml). The existing
-- FORCE RLS tenant_isolation policy (v98) covers the new columns. Idempotent (IF NOT EXISTS and
-- constraints added only when absent); additive, no rewrite of existing rows.

BEGIN;
SET LOCAL lock_timeout = '15s';

ALTER TABLE water_ledger ADD COLUMN IF NOT EXISTS et0_method TEXT;
ALTER TABLE water_ledger ADD COLUMN IF NOT EXISTS et0_quality TEXT;
ALTER TABLE water_ledger ADD COLUMN IF NOT EXISTS weather_snapshot_id TEXT;
ALTER TABLE water_ledger ADD COLUMN IF NOT EXISTS rain_source TEXT;
ALTER TABLE water_ledger ADD COLUMN IF NOT EXISTS taw_mm DOUBLE PRECISION;
ALTER TABLE water_ledger ADD COLUMN IF NOT EXISTS raw_mm DOUBLE PRECISION;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'water_ledger'::regclass AND conname = 'water_ledger_et0_method_check'
    ) THEN
        ALTER TABLE water_ledger ADD CONSTRAINT water_ledger_et0_method_check
            CHECK (et0_method IS NULL
                   OR et0_method IN ('fao56_penman_monteith', 'hargreaves_fallback'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'water_ledger'::regclass AND conname = 'water_ledger_et0_quality_check'
    ) THEN
        ALTER TABLE water_ledger ADD CONSTRAINT water_ledger_et0_quality_check
            CHECK (et0_quality IS NULL OR et0_quality IN ('validated', 'degraded'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'water_ledger'::regclass AND conname = 'water_ledger_rain_source_check'
    ) THEN
        ALTER TABLE water_ledger ADD CONSTRAINT water_ledger_rain_source_check
            CHECK (rain_source IS NULL OR rain_source IN ('forecast', 'observed'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'water_ledger'::regclass AND conname = 'water_ledger_root_zone_check'
    ) THEN
        ALTER TABLE water_ledger ADD CONSTRAINT water_ledger_root_zone_check
            CHECK ((taw_mm IS NULL OR taw_mm > 0)
                   AND (raw_mm IS NULL OR (raw_mm >= 0 AND (taw_mm IS NULL OR raw_mm <= taw_mm))));
    END IF;
END
$$;

COMMENT ON COLUMN water_ledger.et0_method IS
    'v279: weather-service ET0 method for et0_mm (fao56_penman_monteith | hargreaves_fallback); NULL = not declared.';
COMMENT ON COLUMN water_ledger.et0_quality IS
    'v279: weather-service ET0 quality_status (validated | degraded). Only validated Penman-Monteith is reference ET0.';
COMMENT ON COLUMN water_ledger.weather_snapshot_id IS
    'v279: weather_snapshot_id of the ET0 product the row was computed from.';
COMMENT ON COLUMN water_ledger.rain_source IS
    'v279: forecast (written from the day''s forecast) | observed (re-recorded from the weather archive once it has the day).';
COMMENT ON COLUMN water_ledger.taw_mm IS
    'v279: root-zone TAW (mm) the row''s depletion was computed against; NULL = not declared.';
COMMENT ON COLUMN water_ledger.raw_mm IS
    'v279: root-zone RAW (mm) the row''s deficit was computed against; NULL = not declared.';

COMMIT;
