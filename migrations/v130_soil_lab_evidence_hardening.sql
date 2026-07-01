-- v130 (v57.5 line) — Soil lab evidence hardening (retro-hardens the v50 workflow table).
-- v50 stored the whole result as a generic JSONB blob → weak as an evidence source for VRA
-- (v62) and irrigation recommendations, which consume soil_lab_tests. This adds TYPED +
-- VALIDATED analyte columns, sample provenance, chain-of-custody, and re-test versioning,
-- WITHOUT dropping the JSONB `result` (kept as the raw source of truth).
--
-- Additive + idempotent (ADD COLUMN IF NOT EXISTS). RLS already present (v50 tenant_isolation,
-- upgraded to WITH CHECK by v70). Applied after v129. Columns are NULLABLE (progressive
-- enrichment); CHECKs reject physically-impossible values so a bad lab record can't silently
-- drive a prescription.

-- ── core analytes (typed, range-checked; extracted/normalized from `result`) ──
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS ph                  NUMERIC;
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS ec_ds_m             NUMERIC;  -- salinity (dS/m)
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS organic_matter_pct  NUMERIC;
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS nitrogen_ppm        NUMERIC;
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS phosphorus_ppm      NUMERIC;
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS potassium_ppm       NUMERIC;
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS sar                 NUMERIC;  -- sodium adsorption ratio
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS calcium_meq_l       NUMERIC;
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS magnesium_meq_l     NUMERIC;
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS sodium_meq_l        NUMERIC;

-- ── sample provenance ──
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS sample_depth_cm     NUMERIC;
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS sample_method       VARCHAR(16);

-- ── chain of custody ──
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS collector_id        VARCHAR(50);
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS lab_received_at     TIMESTAMPTZ;
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS lab_report_file_id  VARCHAR(50);
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS approved_at         TIMESTAMPTZ;

-- ── re-test versioning (a re-test supersedes a prior result; keep the trail) ──
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS result_version      INTEGER NOT NULL DEFAULT 1;
ALTER TABLE soil_lab_tests ADD COLUMN IF NOT EXISTS supersedes_test_id  VARCHAR(50);

-- ── validation: physically-impossible values are rejected (fail-closed evidence) ──
-- NOT VALID so existing rows are untouched; new/updated rows are enforced. Wrapped in DO
-- blocks for idempotency (no ADD CONSTRAINT IF NOT EXISTS in older PG).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_soil_lab_ph_range') THEN
        ALTER TABLE soil_lab_tests ADD CONSTRAINT chk_soil_lab_ph_range
            CHECK (ph IS NULL OR (ph >= 0 AND ph <= 14)) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_soil_lab_nonneg') THEN
        ALTER TABLE soil_lab_tests ADD CONSTRAINT chk_soil_lab_nonneg CHECK (
            (ec_ds_m            IS NULL OR ec_ds_m            >= 0) AND
            (organic_matter_pct IS NULL OR (organic_matter_pct >= 0 AND organic_matter_pct <= 100)) AND
            (nitrogen_ppm       IS NULL OR nitrogen_ppm       >= 0) AND
            (phosphorus_ppm     IS NULL OR phosphorus_ppm     >= 0) AND
            (potassium_ppm      IS NULL OR potassium_ppm      >= 0) AND
            (sar                IS NULL OR sar                >= 0) AND
            (calcium_meq_l      IS NULL OR calcium_meq_l      >= 0) AND
            (magnesium_meq_l    IS NULL OR magnesium_meq_l    >= 0) AND
            (sodium_meq_l       IS NULL OR sodium_meq_l       >= 0) AND
            (sample_depth_cm    IS NULL OR sample_depth_cm    >= 0) AND
            (result_version     >= 1)
        ) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_soil_lab_sample_method') THEN
        ALTER TABLE soil_lab_tests ADD CONSTRAINT chk_soil_lab_sample_method
            CHECK (sample_method IS NULL OR sample_method IN ('composite', 'grid', 'zone')) NOT VALID;
    END IF;
END $$;

-- ── index: VRA/recommendations pick the freshest published result per field ──
CREATE INDEX IF NOT EXISTS idx_soil_lab_tests_field_status_pub
    ON soil_lab_tests (field_id, status, published_at DESC);

COMMENT ON COLUMN soil_lab_tests.ec_ds_m IS 'التوصيل الكهربائيّ (dS/m) — دليل الملوحة لسياسة الريّ/VRA؛ من نتيجة المختبر.';
COMMENT ON COLUMN soil_lab_tests.result_version IS 'إصدار النتيجة — إعادة الفحص تُنشئ صفّاً بإصدار أعلى يشير عبر supersedes_test_id.';
