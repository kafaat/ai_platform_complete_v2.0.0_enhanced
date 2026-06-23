-- ════════════════════════════════════════════════════════════
-- SAHOOL v32 — المواسم الزراعيّة (Cropping seasons) لكلّ حقل
-- ════════════════════════════════════════════════════════════
-- الفجوة المسدودة: نموذج «إضافة موسم» كان يُرسل إلى /seasons بلا خلفيّة
-- فيُبتلَع الفشل ولا يُخزَّن شيء. هذا الجدول يحفظ الموسم الكامل (نمط FieldView):
-- المحاصيل (تناوب) + الصنف + نوع الريّ + كمية البذور + تواريخ (تسوية/حراثة/بذر/
-- نهاية) + مراحل النمو + الحالة. مربوط بالحقل ومعزول لكلّ مستأجر (RLS).

CREATE TABLE IF NOT EXISTS seasons (
    season_id          VARCHAR(50)  PRIMARY KEY,
    tenant_id          UUID         NOT NULL,
    field_id           VARCHAR(50)  NOT NULL REFERENCES fields(field_id) ON DELETE CASCADE,
    crops              JSONB        NOT NULL DEFAULT '[]'::jsonb,  -- محاصيل الموسم (تناوب)
    cultivar           VARCHAR(100),                              -- الصنف / variety
    irrigation_type    VARCHAR(20),                               -- drip/pivot/flood/sprinkler/rainfed/subsurface
    seed_rate_kg_ha    NUMERIC(8, 2) CHECK (seed_rate_kg_ha IS NULL OR seed_rate_kg_ha >= 0),
    land_leveling_date DATE,
    plowing_date       DATE,
    sowing_date        DATE,                                      -- تاريخ نثر البذور
    season_end         DATE,                                      -- نهاية الموسم / الحصاد المتوقّع
    stages             JSONB        NOT NULL DEFAULT '[]'::jsonb, -- مراحل النمو المخصّصة
    status             VARCHAR(20)  NOT NULL DEFAULT 'active'
        CHECK (status IN ('planned', 'active', 'closed')),
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_seasons_field  ON seasons(field_id);
CREATE INDEX IF NOT EXISTS idx_seasons_tenant ON seasons(tenant_id, status);

DROP TRIGGER IF EXISTS trg_seasons_updated_at ON seasons;
CREATE OR REPLACE TRIGGER trg_seasons_updated_at
    BEFORE UPDATE ON seasons
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

SELECT _sahool_apply_tenant_rls('seasons');

COMMENT ON TABLE seasons IS 'المواسم الزراعيّة لكلّ حقل (محاصيل/صنف/ريّ/تواريخ/مراحل/حالة). نمط FieldView. v32.';
