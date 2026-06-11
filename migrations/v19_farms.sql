-- ════════════════════════════════════════════════════════════
-- SAHOOL v19 — جدول المزارع (Farms) + ربط الحقول بالمزرعة
-- ════════════════════════════════════════════════════════════
-- الفجوة المسدودة (تدقيق التغطية، الطبقة ١): FarmSchema مُعرَّف في
-- canonical_schemas.py لكن لا جدول farms ⇒ لا يمكن تجميع الحقول تحت مزرعة
-- (هرميّة المزرعة→الحقل أساس إدارة المزارع). الحقول موجودة؛ هنا نضيف الأب.
--
-- العزل: RLS على tenant_id عبر الدالّة المشتركة _sahool_apply_tenant_rls.
-- التوافق الخلفي: fields.farm_id يُضاف NULLABLE (الحقول القائمة تبقى بلا مزرعة).

CREATE TABLE IF NOT EXISTS farms (
    farm_id       VARCHAR(50)  PRIMARY KEY,            -- معرّف نصّيّ (يطابق fields.field_id)
    tenant_id     UUID         NOT NULL,
    name          VARCHAR(100) NOT NULL,
    location      VARCHAR(100),                        -- المديريّة/المنطقة
    area_ha       NUMERIC(12, 2),                      -- المساحة الكلّيّة (مجموع الحقول، اختياريّة)
    centroid_lat  NUMERIC(10, 6),
    centroid_lon  NUMERIC(10, 6),
    created_at    TIMESTAMPTZ  DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_farms_tenant ON farms(tenant_id);

-- ربط الحقل بمزرعته (اختياريّ — حقل بلا مزرعة مسموح للتوافق الخلفي).
-- ON DELETE SET NULL: حذف المزرعة لا يحذف حقولها (يفصلها فقط).
ALTER TABLE fields
    ADD COLUMN IF NOT EXISTS farm_id VARCHAR(50)
    REFERENCES farms(farm_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_fields_farm ON fields(farm_id);

-- تحديث updated_at تلقائيّاً (نفس دالّة بقيّة الجداول)
DROP TRIGGER IF EXISTS trg_farms_updated_at ON farms;
CREATE TRIGGER trg_farms_updated_at
    BEFORE UPDATE ON farms
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- عزل المستأجرين (بعد v9_rls_force_all، self-applied آمن — كنمط v15/v16)
SELECT _sahool_apply_tenant_rls('farms');

COMMENT ON TABLE farms IS 'المزارع — أب الحقول (هرميّة المزرعة→الحقل). v19.';
