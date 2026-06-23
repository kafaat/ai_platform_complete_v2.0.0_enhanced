-- ════════════════════════════════════════════════════════════
-- SAHOOL v26 — البيانات المرجعيّة (Master Data) + الدورات الزراعيّة
-- ════════════════════════════════════════════════════════════
-- الفجوة المسدودة (تدقيق التغطية + نموذج Agricultural OS): لا كتالوج مركزيّ
-- للكيانات المرجعيّة (محاصيل/تربة/أسمدة/مبيدات/أصناف بذور/أنواع معدّات)، ولا
-- تتبّع للدورات الزراعيّة (تسلسل المحاصيل عبر المواسم — أساس التتبّع والتخطيط).
--   • master_data    — كتالوج موحّد (category + code + اسم + بيانات وصفيّة)
--   • crop_rotations — سجلّ تعاقب المحاصيل لكلّ حقل (للدورة الزراعيّة والتتبّع)
-- العزل: RLS لكلّ مستأجر (كلّ مستأجر يُدير كتالوجه).

-- ── master_data: الكتالوج المرجعيّ الموحّد ───────────────────
CREATE TABLE IF NOT EXISTS master_data (
    md_id      VARCHAR(50)  PRIMARY KEY,
    tenant_id  UUID         NOT NULL,
    category   VARCHAR(24)  NOT NULL
        CHECK (category IN ('crop', 'soil_type', 'fertilizer', 'pesticide',
                            'seed_variety', 'equipment_type', 'other')),
    code       VARCHAR(60)  NOT NULL,                  -- معرّف مقروء (wheat_durum)
    name_ar    VARCHAR(160) NOT NULL,
    name_en    VARCHAR(160),
    metadata   JSONB        NOT NULL DEFAULT '{}'::jsonb,
    active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- لا تكرار للرمز ضمن نفس المستأجر+الفئة
    UNIQUE (tenant_id, category, code)
);
CREATE INDEX IF NOT EXISTS idx_master_data_cat ON master_data(tenant_id, category) WHERE active;

DROP TRIGGER IF EXISTS trg_master_data_updated_at ON master_data;
CREATE OR REPLACE TRIGGER trg_master_data_updated_at
    BEFORE UPDATE ON master_data
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── crop_rotations: تعاقب المحاصيل لكلّ حقل ──────────────────
CREATE TABLE IF NOT EXISTS crop_rotations (
    rotation_id    VARCHAR(50)  PRIMARY KEY,
    tenant_id      UUID         NOT NULL,
    field_id       VARCHAR(50)  NOT NULL REFERENCES fields(field_id) ON DELETE CASCADE,
    crop           VARCHAR(80)  NOT NULL,              -- اسم/رمز المحصول (قد يطابق master_data.code)
    season_label   VARCHAR(40),                        -- "2026-ربيع" مثلاً
    sequence_order INTEGER,                            -- ترتيب التعاقب (1،2،3...)
    planted_at     DATE,
    harvested_at   DATE,
    notes          TEXT,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_crop_rot_field
    ON crop_rotations(field_id, sequence_order);
CREATE INDEX IF NOT EXISTS idx_crop_rot_tenant ON crop_rotations(tenant_id);

DROP TRIGGER IF EXISTS trg_crop_rot_updated_at ON crop_rotations;
CREATE OR REPLACE TRIGGER trg_crop_rot_updated_at
    BEFORE UPDATE ON crop_rotations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- عزل المستأجرين (self-applied بعد force_all)
SELECT _sahool_apply_tenant_rls('master_data');
SELECT _sahool_apply_tenant_rls('crop_rotations');

COMMENT ON TABLE master_data    IS 'كتالوج البيانات المرجعيّة الموحّد (محاصيل/تربة/أسمدة/مبيدات/بذور). v26.';
COMMENT ON TABLE crop_rotations IS 'تعاقب المحاصيل لكلّ حقل (الدورة الزراعيّة + التتبّع). v26.';
