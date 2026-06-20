-- migrations/v78_decision_record.sql
--
-- إدامة رأس القرار (Decision→Outcome→Evidence→Learning، P0-1/P0-3 في تقرير الفجوات):
-- المنصّة **تعرف كيف تتّخذ القرار** (crop-twin/decision، irrigation-plan، profit-aware)
-- وتُسَكّ لكلّ قرار decision_id ونَسَباً (lineage)، لكنّ القرار **لا يُدام** في قاعدة
-- البيانات — يُحسَب ويُعرَض ويُنسى. فلا سلسلة قابلة للتدقيق تربط القرار بنتيجته لاحقاً.
--
-- هذا الجدول يُدِيم **رأس** السلسلة: كلّ قرار مُتّخذ (decision_id، نوعه، حقله، قيمته
-- الكاملة JSONB، ثقته) — ليُربَط به outcome_record لاحقاً (v79) عبر decision_id.
-- لا يستبدل المنطق النقيّ (الحساب يبقى نقيّاً بلا قاعدة)؛ يُدِيم ناتجه للتراكم المعرفيّ.
--
--   • decision_id VARCHAR(40) PRIMARY KEY (المعرّف الموحّد dec_…؛ ON CONFLICT DO NOTHING).
--   • tenant_id UUID NOT NULL ⇒ عزل المستأجِر عبر RLS+FORCE بسياسة current_setting
--     (تطابق حُرّاس test_rls_*/sahool_inspector؛ الكتابة عبر sahool_app NOBYPASSRLS).
--   • decision_value JSONB (القرار الكامل كما عُرِض)؛ confidence الناقص NULL (لا تلفيق).
--   • يُصدِر مساره حدث DECISION_RECORDED عبر outbox (event_bus) ضمن نفس المعاملة.
-- idempotent (CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS قبل CREATE POLICY).

BEGIN;

CREATE TABLE IF NOT EXISTS decision_record (
    decision_id     VARCHAR(40)  PRIMARY KEY,             -- معرّف القرار الموحّد (dec_…)
    tenant_id       UUID         NOT NULL,                -- عزل المستأجر (RLS أدناه)
    field_id        VARCHAR(50),                          -- الحقل (اختياريّ)
    decision_type   VARCHAR(60)  NOT NULL,                -- crop_twin | irrigation_plan | profit_aware …
    region          VARCHAR(40),                          -- المنطقة اليمنيّة (للمعايرة/الدليل)
    stage           VARCHAR(24)  NOT NULL DEFAULT 'decision', -- مرحلة النَّسَب (رأس السلسلة)
    decision_value  JSONB        NOT NULL,                -- القرار الكامل (الناتج النقيّ) كما عُرِض
    confidence      DOUBLE PRECISION,                     -- ثقة القرار إن توفّرت (وإلا NULL — لا تلفيق)
    created_by      VARCHAR(80),                          -- من اتّخذ القرار (مستخدم/نظام)
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_decision_record_tenant  ON decision_record (tenant_id);
CREATE INDEX IF NOT EXISTS idx_decision_record_field   ON decision_record (tenant_id, field_id);
CREATE INDEX IF NOT EXISTS idx_decision_record_created ON decision_record (created_at DESC);

COMMENT ON TABLE  decision_record IS
    'سجلّ القرارات الزراعيّة المُدام — رأس سلسلة النَّسَب (Decision→Outcome→Evidence). tenant-isolated عبر RLS. v78.';
COMMENT ON COLUMN decision_record.decision_value IS 'القرار الكامل (الناتج النقيّ) كما عُرِض — JSONB.';
COMMENT ON COLUMN decision_record.confidence     IS 'ثقة القرار إن توفّرت، وإلا NULL (لا تلفيق).';

-- ── RLS+FORCE + سياسة tenant_isolation (current_setting — تطابق الحُرّاس) ──
ALTER TABLE decision_record ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_record FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON decision_record;
CREATE POLICY tenant_isolation ON decision_record
USING (
    tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR tenant_id::TEXT = current_setting('app.current_tenant', true)
);

COMMIT;
