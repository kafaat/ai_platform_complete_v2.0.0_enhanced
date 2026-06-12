-- v49: تفعيل الربط الحيّ لميزات #62/#63 المبنيّة.
--   (1) عمود zone_key على fields — مفتاح الإقليم الزراعي-المناخي القانوني (يطابق
--       agro_climate_zones: western_highlands/tihama/...) — يُفعّل crop-gap +
--       classification-readiness. (يختلف عن climate_zone v37 الوصفيّ.)
--   (2) جدول recommendation_outcomes — أزواج (توقّع,نتيجة) لكلّ توصية — يُفعّل
--       prediction-calibration + بوّابة تفعيل التعلّم. RLS لكلّ مستأجِر.
-- كلّها idempotent + آمنة (IF NOT EXISTS) + RLS مطابق لنمط init_v8 (tenant_id UUID).

-- ── (1) zone_key على fields ──────────────────────────────────────
ALTER TABLE fields ADD COLUMN IF NOT EXISTS zone_key VARCHAR(64);
COMMENT ON COLUMN fields.zone_key IS
    'مفتاح الإقليم الزراعي-المناخي القانوني (agro_climate_zones) — للتجميع الإقليمي';
CREATE INDEX IF NOT EXISTS idx_fields_zone_key ON fields (zone_key) WHERE zone_key IS NOT NULL;

-- ── (2) recommendation_outcomes ──────────────────────────────────
-- أزواج (توقّع غلّة, نتيجة فعليّة) + إشارات النضج/القبول (لتفعيل التعلّم بصدق).
CREATE TABLE IF NOT EXISTS recommendation_outcomes (
    outcome_id           BIGSERIAL    PRIMARY KEY,
    tenant_id            UUID,                       -- RLS (لا فلترة تطبيقيّة)
    field_id             VARCHAR(50),
    farm_id              VARCHAR(50),                -- وحدة التكرار (pseudoreplication)
    season_id            VARCHAR(50),
    crop                 VARCHAR(50),
    recommendation_id    VARCHAR(64),                -- ربط التوصية الأصليّة
    predicted_yield_t_ha NUMERIC(8,3),               -- التوقّع
    actual_yield_t_ha    NUMERIC(8,3),               -- النتيجة الفعليّة (NULL=لم تكتمل)
    accepted             BOOLEAN      NOT NULL DEFAULT FALSE,  -- قبل المزارع التوصية؟
    matured_within_lag   BOOLEAN      NOT NULL DEFAULT FALSE,  -- نضجت ضمن نافذة زمنيّة صحيحة؟
    issued_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    outcome_recorded_at  TIMESTAMPTZ                            -- متى سُجّلت النتيجة
);
CREATE INDEX IF NOT EXISTS idx_reco_outcomes_tenant ON recommendation_outcomes (tenant_id);
CREATE INDEX IF NOT EXISTS idx_reco_outcomes_crop   ON recommendation_outcomes (crop);
CREATE INDEX IF NOT EXISTS idx_reco_outcomes_field  ON recommendation_outcomes (field_id);

-- RLS لكلّ مستأجِر (مطابق نمط init_v8 — tenant_id UUID).
ALTER TABLE recommendation_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendation_outcomes FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON recommendation_outcomes;
CREATE POLICY tenant_isolation ON recommendation_outcomes
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);
