-- migrations/v84_calibration_audit.sql
--
-- سجلّ تدقيق المعايرة (Calibration Audit Trail) — جدول append-only يُدوّن كلّ تغيير
-- على calibration_override (v80): تثبيت تجاوز (override_set)، تطبيق تكيّف آليّ محروس
-- بالدليل (adaptation_applied)، أو عَكْس/حذف التجاوز (reverted). يُغلق فجوة «من غيّر
-- المعايرة، متى، وما القيم قبل/بعد؟» فيصبح كلّ تغيير معايرة متتبَّعاً ومدقَّقاً.
--
--   • append-only: لا UPDATE ولا DELETE (لا عمود updated_at، ولا مسار يُعدّل/يمحو) —
--     سجلّ التدقيق لا يُعدَّل ولا يُمحى (نزاهة التدقيق).
--   • action TEXT CHECK ⇒ مجموعة مغلقة من الأفعال (لا فعل مُلفّق).
--   • old_values/new_values JSONB: لقطة القيم قبل/بعد (old قد تكون NULL إن تعذّرت
--     قراءة السابق قبل الـupsert — لا تلفيق).
--   • tenant_id UUID NOT NULL ⇒ عزل المستأجِر عبر RLS+FORCE بسياسة current_setting.
--   • فهرس (tenant_id, region, created_at DESC) ⇒ جلب سجلّ المنطقة بالأحدث أوّلاً.
-- idempotent (CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS قبل CREATE POLICY).

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS calibration_audit (
    audit_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID         NOT NULL,                 -- عزل المستأجر (RLS أدناه)
    region      VARCHAR(40),                           -- مفتاح المنطقة المُطبَّع (jawf/tihama/…)
    action      TEXT         NOT NULL                  -- الفعل المُدقَّق (مجموعة مغلقة)
                CHECK (action IN ('override_set', 'reverted', 'adaptation_applied')),
    old_values  JSONB,                                 -- لقطة القيم السابقة (NULL إن تعذّرت قراءتها)
    new_values  JSONB,                                 -- لقطة القيم الجديدة (قد تكون NULL عند الحذف)
    source_ar   TEXT,                                  -- مصدر/سبب التغيير (provenance)
    actor       VARCHAR(80),                           -- من نفّذ التغيير
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()    -- زمن القيد (append-only: لا updated_at)
);

-- جلب سجلّ منطقة المستأجِر بالأحدث أوّلاً.
CREATE INDEX IF NOT EXISTS idx_calibration_audit_tenant_region
    ON calibration_audit (tenant_id, region, created_at DESC);

COMMENT ON TABLE  calibration_audit IS
    'سجلّ تدقيق المعايرة append-only (لا UPDATE/DELETE): override_set/reverted/adaptation_applied. tenant-isolated عبر RLS. v84.';
COMMENT ON COLUMN calibration_audit.old_values IS 'لقطة القيم السابقة — NULL إن تعذّرت قراءتها قبل الكتابة (لا تلفيق).';
COMMENT ON COLUMN calibration_audit.new_values IS 'لقطة القيم الجديدة (NULL عند الحذف/العَكْس).';

-- ── RLS+FORCE + سياسة tenant_isolation (current_setting — تطابق الحُرّاس) ──
ALTER TABLE calibration_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE calibration_audit FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON calibration_audit;
CREATE POLICY tenant_isolation ON calibration_audit
USING (
    tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR tenant_id::TEXT = current_setting('app.current_tenant', true)
);

COMMIT;
