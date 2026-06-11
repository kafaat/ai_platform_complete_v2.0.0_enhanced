-- ════════════════════════════════════════════════════════════
-- SAHOOL v28 — الإعدادات (Settings): منصّة/مزرعة/ريّ/إشعارات
-- ════════════════════════════════════════════════════════════
-- الفجوة المسدودة: لا مخزن موحّد لإعدادات المستأجر (تفضيلات المنصّة، إعدادات
-- المزرعة، حدود الريّ الافتراضيّة، قنوات الإشعارات). كلّ مستأجر يضبط نطاقاته.
--   • settings — مفتاح/قيمة (JSONB) مُنطّقة بـscope، فريدة لكلّ (مستأجر+نطاق+مفتاح)
-- العزل: RLS لكلّ مستأجر.

CREATE TABLE IF NOT EXISTS settings (
    setting_id VARCHAR(50)  PRIMARY KEY,
    tenant_id  UUID         NOT NULL,
    scope      VARCHAR(20)  NOT NULL
        CHECK (scope IN ('platform', 'farm', 'irrigation', 'notification')),
    key        VARCHAR(80)  NOT NULL,
    value      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    updated_by VARCHAR(100),
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, scope, key)
);
CREATE INDEX IF NOT EXISTS idx_settings_scope ON settings(tenant_id, scope);

DROP TRIGGER IF EXISTS trg_settings_updated_at ON settings;
CREATE TRIGGER trg_settings_updated_at
    BEFORE UPDATE ON settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

SELECT _sahool_apply_tenant_rls('settings');

COMMENT ON TABLE settings IS 'مخزن الإعدادات الموحّد (منصّة/مزرعة/ريّ/إشعارات) مُنطّق بـscope. v28.';
