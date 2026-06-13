-- v50: Workflow مخبري للتربة (Soil lab tests) — دورة حياة موثَّقة بدل أعمدة soil_* ثابتة.
--   عيّنة → مختبر → نتيجة → اعتماد → نشر (+رفض/إلغاء). حالة + نتيجة JSONB + اعتماد.
--   مربوط بالحقل، معزول لكلّ مستأجِر (RLS). قواعد الانتقال في core/engines/soil_lab_workflow.
--   idempotent + آمن (IF NOT EXISTS) + RLS مطابق نمط init_v8 (tenant_id UUID). v50.

CREATE TABLE IF NOT EXISTS soil_lab_tests (
    test_id      VARCHAR(50)  PRIMARY KEY,
    tenant_id    UUID         NOT NULL,
    field_id     VARCHAR(50)  NOT NULL REFERENCES fields(field_id) ON DELETE CASCADE,
    status       VARCHAR(24)  NOT NULL DEFAULT 'requested'
        CHECK (status IN ('requested', 'sampled', 'in_lab', 'result_received',
                          'approved', 'published', 'rejected', 'cancelled')),
    lab_name     VARCHAR(120),                                 -- اسم المختبر
    sampled_on   DATE,                                         -- تاريخ جمع العيّنة
    result       JSONB        NOT NULL DEFAULT '{}'::jsonb,    -- نتائج (ph/ec/n/p/k/om…)
    notes_ar     TEXT,
    approved_by  VARCHAR(50),                                  -- المهندس المعتمِد
    published_at TIMESTAMPTZ,                                  -- وقت النشر (مرجعيّة الحقل)
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_soil_lab_tests_field  ON soil_lab_tests (field_id);
CREATE INDEX IF NOT EXISTS idx_soil_lab_tests_tenant ON soil_lab_tests (tenant_id, status);

DROP TRIGGER IF EXISTS trg_soil_lab_tests_updated_at ON soil_lab_tests;
CREATE TRIGGER trg_soil_lab_tests_updated_at
    BEFORE UPDATE ON soil_lab_tests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- RLS لكلّ مستأجِر (مطابق نمط init_v8 — tenant_id UUID).
ALTER TABLE soil_lab_tests ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_lab_tests FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON soil_lab_tests;
CREATE POLICY tenant_isolation ON soil_lab_tests
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID);

COMMENT ON TABLE soil_lab_tests IS
    'دورة حياة فحص التربة المخبري (عيّنة→مختبر→نتيجة→اعتماد→نشر). نمط seasons/activities. v50.';
