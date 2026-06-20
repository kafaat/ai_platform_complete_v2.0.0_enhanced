-- migrations/v79_outcome_record.sql
--
-- إدامة نتيجة القرار (P0-1 في تقرير الفجوات): نقطة /outcome/measure **تقيس** نتيجة
-- القرار (مُخطَّط مقابل مرصود) لكنّها **لا تُدِيمها** — فالقياس يُعرَض ويُنسى، ولا يتراكم
-- دليل ميدانيّ يربط القرار بنتيجته (الأساس الذي يبني عليه evidence_registry ثمّ
-- learning_feedback ثمّ adaptive_calibration). هذا الجدول يُدِيم كلّ قياس نتيجة.
--
--   • outcome_id VARCHAR(40) PRIMARY KEY (المعرّف out_…).
--   • decision_id VARCHAR(40) NOT NULL مفهرس — جوهر النَّسَب (الانضمام Decision→Outcome).
--     الربط **ليّن** (بلا قيد FK صلب) عمداً: (١) القياس قد يَرِد لقرار حُسِب عبر المسار
--     النقيّ دون إدامة (توافق خلفيّ)، (٢) قيد FK يتحقّق بصلاحيّة المالك متجاوزاً RLS —
--     تجنّبه يحفظ عزل المستأجرين صرفاً. الربط المنطقيّ مكفول بـdecision_id الفريد.
--   • tenant_id UUID NOT NULL ⇒ عزل المستأجِر عبر RLS+FORCE بسياسة current_setting.
--   • planned/actual/metrics JSONB؛ success BOOLEAN (NULL إن تعذّر الحسم — لا تلفيق).
--   • يُصدِر مساره حدث OUTCOME_MEASURED عبر outbox (event_bus) ضمن نفس المعاملة.
-- idempotent (CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS قبل CREATE POLICY).

BEGIN;

CREATE TABLE IF NOT EXISTS outcome_record (
    outcome_id      VARCHAR(40)  PRIMARY KEY,             -- معرّف القياس (out_…)
    tenant_id       UUID         NOT NULL,                -- عزل المستأجر (RLS أدناه)
    decision_id     VARCHAR(40)  NOT NULL,                -- القرار المقيس (نَسَب — ربط ليّن، انظر الرأس)
    field_id        VARCHAR(50),                          -- الحقل (اختياريّ)
    region          VARCHAR(40),                          -- المنطقة اليمنيّة (لتجميع الدليل لاحقاً)
    stage           VARCHAR(24)  NOT NULL DEFAULT 'outcome',  -- مرحلة النَّسَب
    planned         JSONB        NOT NULL,                -- ما خُطِّط له (من القرار/الخطّة)
    actual          JSONB        NOT NULL,                -- ما رُصِد ميدانيّاً
    metrics         JSONB        NOT NULL,                -- مخرجات measure_outcome (نجاح/إجهاد/وفر …)
    success         BOOLEAN,                              -- خلاصة النجاح إن أمكن حسمها، وإلا NULL
    created_by      VARCHAR(80),                          -- من سجّل القياس
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_outcome_record_tenant   ON outcome_record (tenant_id);
CREATE INDEX IF NOT EXISTS idx_outcome_record_decision ON outcome_record (decision_id);
CREATE INDEX IF NOT EXISTS idx_outcome_record_field    ON outcome_record (tenant_id, field_id);
CREATE INDEX IF NOT EXISTS idx_outcome_record_created  ON outcome_record (created_at DESC);

COMMENT ON TABLE  outcome_record IS
    'سجلّ نتائج القرارات المُدام — يُغلق حلقة Decision→Outcome (P0-1). tenant-isolated عبر RLS. v79.';
COMMENT ON COLUMN outcome_record.decision_id IS 'القرار المقيس — ربط نَسَب ليّن (عمود مفهرس بلا FK صلب، يحفظ RLS).';
COMMENT ON COLUMN outcome_record.metrics     IS 'مخرجات measure_outcome (المقاييس المتوفّر طرفاها فقط؛ الناقص needs_data).';
COMMENT ON COLUMN outcome_record.success     IS 'خلاصة النجاح إن أمكن حسمها، وإلا NULL (لا تلفيق).';

-- ── RLS+FORCE + سياسة tenant_isolation (current_setting — تطابق الحُرّاس) ──
ALTER TABLE outcome_record ENABLE ROW LEVEL SECURITY;
ALTER TABLE outcome_record FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON outcome_record;
CREATE POLICY tenant_isolation ON outcome_record
USING (
    tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR tenant_id::TEXT = current_setting('app.current_tenant', true)
);

COMMIT;
