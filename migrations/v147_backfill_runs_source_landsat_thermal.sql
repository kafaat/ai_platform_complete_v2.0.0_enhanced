-- migrations/v147_backfill_runs_source_landsat_thermal.sql
--
-- v147: مصدر backfill صريح كي لا تختلط تشغيلة Sentinel-2/Copernicus مع تشغيلة
-- Landsat الحرارية. Landsat في Sahool طبقة thermal_unique فقط (LST مباشر، ومؤشرات
-- CWSI/TVDI/TCI/VHI مشتقة لاحقاً)، لذلك يحتاج العامل معرفة source بدل افتراض Sentinel.
-- Idempotent؛ بعد v146.

BEGIN;

ALTER TABLE backfill_runs
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'sentinel-2';

ALTER TABLE backfill_runs DROP CONSTRAINT IF EXISTS backfill_runs_source_check;
ALTER TABLE backfill_runs
    ADD CONSTRAINT backfill_runs_source_check
    CHECK (source IN ('sentinel-2', 'landsat-thermal'));

CREATE INDEX IF NOT EXISTS idx_backfill_runs_source_status
    ON backfill_runs (source, status, created_at);

COMMIT;
