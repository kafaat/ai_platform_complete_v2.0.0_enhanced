-- ════════════════════════════════════════════════════════════
-- SAHOOL v29 — سجلّ مستندات (Document Management metadata registry)
-- ════════════════════════════════════════════════════════════
-- الفجوة المسدودة: لا سجلّ موحّد للمستندات (عقود/تقارير/صور/خرائط/نتائج مختبر)
-- مربوطة بالحقول مع تحكّم وصول (RLS لكلّ مستأجر + RBAC على الطبقة API).
--
-- ⚠️ هذا سجلّ بيانات وصفيّة (metadata) فقط — لا يخزّن الملفّ الثنائيّ (blob)
--    نفسه. تخزين الكائنات الفعليّ (PDF/صورة/...) يحتاج S3/MinIO؛ نحفظ هنا
--    البيانات الوصفيّة + storage_ref (مسار/رابط للكائن في تخزين الكائنات).
-- العزل: RLS لكلّ مستأجر (self-applied بعد force_all).

CREATE TABLE IF NOT EXISTS documents (
    doc_id       VARCHAR(50)  PRIMARY KEY,
    tenant_id    UUID         NOT NULL,
    category     VARCHAR(20)  NOT NULL
        CHECK (category IN ('contract', 'report', 'image',
                            'map', 'lab_result', 'other')),
    field_id     VARCHAR(50)  REFERENCES fields(field_id) ON DELETE SET NULL,
    title        VARCHAR(200) NOT NULL,
    storage_ref  TEXT,                                  -- مسار/رابط للكائن في تخزين الكائنات (S3/MinIO)
    content_type VARCHAR(80),                           -- MIME (application/pdf, image/jpeg ...)
    size_bytes   BIGINT       CHECK (size_bytes IS NULL OR size_bytes >= 0),
    version      INTEGER      NOT NULL DEFAULT 1,
    uploaded_by  VARCHAR(100),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_documents_cat   ON documents(tenant_id, category);
CREATE INDEX IF NOT EXISTS idx_documents_field ON documents(field_id);

DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents;
CREATE OR REPLACE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

SELECT _sahool_apply_tenant_rls('documents');

COMMENT ON TABLE documents IS 'سجلّ بيانات وصفيّة للمستندات (عقود/تقارير/صور/خرائط/نتائج مختبر) + مرجع تخزين الكائن. لا blob. v29.';
