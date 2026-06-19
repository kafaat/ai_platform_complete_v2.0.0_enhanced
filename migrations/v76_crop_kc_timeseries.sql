-- migrations/v76_crop_kc_timeseries.sql
--
-- تخزين Kc الدائم — جدول crop_kc_timeseries: يحفظ معاملات Kc الثلاثيّة (FAO-56)
-- المُشتقّة من محاكاة WOFOST (kc_extraction_engine: CFET+تنعيم) لكلّ
-- (حقل × محصول × موسم × سيناريو) — فيصبح Kc قابلاً للمقارنة التاريخيّة عبر المواسم
-- بدل إعادة حسابه كلّ مرّة بلا أثر. يكمّل جسر kc_to_fao56_bridge (الذي يُغذّي الريّ).
--
--   • field_id نصّ (TEXT) لا UUID — يطابق fields.field_id VARCHAR(50) (راجع v18/v74/v75).
--   • tenant_id UUID NOT NULL ⇒ عزل المستأجِر عبر RLS+FORCE بسياسة current_setting
--     (تطابق حُرّاس test_rls_*؛ الكتابة عبر sahool_app NOBYPASSRLS لا superuser).
--   • scenario_type قيمة مُقيَّدة (CHECK): potential (ريّ كامل، الافتراضيّ للاشتقاق) /
--     actual (تحت الإجهاد) / full_irrigation / deficit.
--   • قيم Kc nullable (مرحلة قد تكون ناقصة في موسم قصير) — لا نختلق.
--   • UNIQUE(tenant_id, field_id, crop_id, season_id, scenario_type) ⇒ upsert لا تكرار.
-- idempotent (CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS قبل CREATE POLICY).

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS crop_kc_timeseries (
    kc_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL,
    field_id       TEXT NOT NULL,
    crop_id        TEXT NOT NULL,
    season_id      TEXT NOT NULL,
    scenario_type  TEXT NOT NULL DEFAULT 'potential' CHECK (
                       scenario_type IN ('potential', 'actual', 'full_irrigation', 'deficit')
                   ),
    kc_ini         DOUBLE PRECISION,
    kc_mid         DOUBLE PRECISION,
    kc_end         DOUBLE PRECISION,
    kcb_ini        DOUBLE PRECISION,
    kcb_mid        DOUBLE PRECISION,
    kcb_end        DOUBLE PRECISION,
    cfet           DOUBLE PRECISION DEFAULT 1.0,
    source         TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_crop_kc_scenario
        UNIQUE (tenant_id, field_id, crop_id, season_id, scenario_type)
);
CREATE INDEX IF NOT EXISTS idx_crop_kc_field ON crop_kc_timeseries(tenant_id, field_id);
CREATE INDEX IF NOT EXISTS idx_crop_kc_crop_season ON crop_kc_timeseries(crop_id, season_id);

-- ── RLS+FORCE + سياسة tenant_isolation (current_setting — تطابق الحُرّاس) ──
ALTER TABLE crop_kc_timeseries ENABLE ROW LEVEL SECURITY;
ALTER TABLE crop_kc_timeseries FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON crop_kc_timeseries;
CREATE POLICY tenant_isolation ON crop_kc_timeseries
USING (
    tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR tenant_id::TEXT = current_setting('app.current_tenant', true)
);

COMMIT;
