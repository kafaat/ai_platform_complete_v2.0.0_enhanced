-- migrations/v80_calibration_override.sql
--
-- معايرة إقليميّة مُدارة DB-backed (يُكمل البند 3 من تقرير الفجوات): حتى الآن قيم
-- المعايرة الإقليميّة (_REGION_OVERRIDES) في الكود وفارغة عمداً (مبدأ الصدق: لا قيم
-- يمنيّة مُلفّقة) — فالمنطقة تبقى validated=false حتى يُعدَّل الكود يدويّاً. هذا الجدول
-- يجعل المعايرة **قابلة للإدارة لكلّ مستأجِر** دون تعديل كود: يُدِيم قيمه المُتحقَّقة
-- (المقبولة عبر validate_region_calibration، مع مصدر provenance) في القاعدة.
--
--   • UNIQUE(tenant_id, region) ⇒ ملفّ مُدار واحد لكلّ منطقة لكلّ مستأجِر (upsert).
--   • override_values JSONB: الحقول المقبولة فقط (لا يُكتب مرفوض ولا مُلفّق).
--   • tenant_id UUID NOT NULL ⇒ عزل المستأجِر عبر RLS+FORCE بسياسة current_setting.
--   • عكوسيّ: DELETE يُعيد المنطقة للوراثة العامّة (لا حالة خفيّة دائمة).
--   • يُصدِر مساره حدث CALIBRATION_OVERRIDE_SET عبر outbox (event_bus) ضمن المعاملة.
-- idempotent (CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS قبل CREATE POLICY).

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS calibration_override (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID         NOT NULL,                -- عزل المستأجر (RLS أدناه)
    region          VARCHAR(40)  NOT NULL,               -- مفتاح المنطقة المُطبَّع (jawf/tihama/…)
    override_values JSONB        NOT NULL,               -- القيم المُتحقَّقة المقبولة فقط
    source_ar       TEXT,                                -- مصدر القياس (provenance — إلزاميّ للتحقّق)
    validated       BOOLEAN      NOT NULL DEFAULT FALSE, -- مُتحقَّق (قيم مقبولة + مصدر)
    created_by      VARCHAR(80),                         -- من أدام المعايرة
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, region)                           -- ملفّ مُدار واحد لكلّ منطقة (upsert)
);

CREATE INDEX IF NOT EXISTS idx_calibration_override_tenant ON calibration_override (tenant_id);

COMMENT ON TABLE  calibration_override IS
    'معايرة إقليميّة مُدارة DB-backed لكلّ مستأجِر (يُكمل البند 3). tenant-isolated عبر RLS. v80.';
COMMENT ON COLUMN calibration_override.override_values IS 'القيم المُتحقَّقة المقبولة فقط (لا مرفوض ولا مُلفّق).';
COMMENT ON COLUMN calibration_override.source_ar       IS 'مصدر القياس (provenance) — إلزاميّ لاعتبار المعايرة مُتحقَّقة.';

-- ── RLS+FORCE + سياسة tenant_isolation (current_setting — تطابق الحُرّاس) ──
ALTER TABLE calibration_override ENABLE ROW LEVEL SECURITY;
ALTER TABLE calibration_override FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON calibration_override;
CREATE POLICY tenant_isolation ON calibration_override
USING (
    tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR tenant_id::TEXT = current_setting('app.current_tenant', true)
);

COMMIT;
