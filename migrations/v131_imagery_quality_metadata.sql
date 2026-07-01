-- v131 (v57.5 line) — imagery quality metadata (completes the v54 gap on raster_assets).
-- v14 gave scene_id/acquisition_date/cloud_pct; v105 added aoi_cloud_pct/quality_score/
-- cloud_mask_sources. Still missing were the trust signals that decide whether an index COG
-- is fit to drive VRA/zoning: how much of the scene is usable after cloud+nodata masking,
-- how much of the field geometry the scene actually covers, and per-index quality flags.
-- Additive + idempotent. RLS already on raster_assets (tenant_id). Applied after v130.

ALTER TABLE raster_assets ADD COLUMN IF NOT EXISTS valid_pixel_ratio   NUMERIC;  -- 0..1 usable after mask
ALTER TABLE raster_assets ADD COLUMN IF NOT EXISTS coverage_ratio      NUMERIC;  -- 0..1 field geom covered
ALTER TABLE raster_assets ADD COLUMN IF NOT EXISTS index_quality_flags JSONB DEFAULT '[]'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_raster_quality_ratios') THEN
        ALTER TABLE raster_assets ADD CONSTRAINT chk_raster_quality_ratios CHECK (
            (valid_pixel_ratio IS NULL OR (valid_pixel_ratio >= 0 AND valid_pixel_ratio <= 1)) AND
            (coverage_ratio    IS NULL OR (coverage_ratio    >= 0 AND coverage_ratio    <= 1))
        ) NOT VALID;
    END IF;
END $$;

-- Freshest, cleanest, most-covered index per field (VRA/zoning evidence pick).
CREATE INDEX IF NOT EXISTS idx_raster_assets_quality_full
    ON raster_assets (tenant_id, field_id, index_name, acquisition_date DESC,
                      valid_pixel_ratio DESC NULLS LAST, cloud_pct ASC);

COMMENT ON COLUMN raster_assets.valid_pixel_ratio IS
    'نسبة البكسلات الصالحة بعد قناع الغيوم/nodata (0..1) — بوّابة ثقة لبناء VRA/المناطق على المؤشّر.';
COMMENT ON COLUMN raster_assets.coverage_ratio IS
    'نسبة تغطية هندسة الحقل بالمشهد (0..1) — مشهد بتغطية جزئيّة لا يُعتمَد للوصفة.';
