-- migrations/v53_field_state_projection.sql
-- إسقاط الحالة القانونيّة الموحّدة للحقل (Canonical Field State — read model).
--
-- مصدر الحقيقة الواحد للحالة الزراعيّة: جدول إسقاط (projection) يُعاد حسابه من
-- المصادر القانونيّة (نضارة NDVI/تربة/طقس) عبر recompute_field_state، ويُحدَّث عند
-- كلّ حدث يغيّر مدخلات القرار (إنشاء موسم/نشر فحص تربة/تحديث طقس). كلّ المستهلكين
-- (التوصيات/التنبيهات/guardrails) يقرؤونه بدل إعادة الحساب المتفرّق.
--
-- ليس event log (ذاك جدول events غير القابل للتعديل) — هذا read model قابل
-- للتحديث (UPSERT). idempotent: إعادة التطبيق كلّ إقلاع آمنة.

CREATE TABLE IF NOT EXISTS field_state (
    field_id           VARCHAR(50)  PRIMARY KEY
                       REFERENCES fields(field_id) ON DELETE CASCADE,
    tenant_id          UUID         NOT NULL,
    validity           VARCHAR(16)  NOT NULL,   -- valid/degraded/conflicted/insufficient
    execution_mode     VARCHAR(16)  NOT NULL,   -- auto/human_review/blocked
    confidence_level   VARCHAR(16),
    ndvi_age_days      DOUBLE PRECISION,
    soil_age_days      DOUBLE PRECISION,
    weather_age_hours  DOUBLE PRECISION,
    reasons_ar         JSONB        NOT NULL DEFAULT '[]'::jsonb,
    conflicts          JSONB        NOT NULL DEFAULT '[]'::jsonb,
    freshness_warnings JSONB        NOT NULL DEFAULT '[]'::jsonb,
    inputs             JSONB        NOT NULL DEFAULT '{}'::jsonb,
    computed_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- عزل المستأجِر (نفس النمط القانونيّ للمنصّة). USING تُستخدَم أيضاً كـWITH CHECK
-- عند غيابها ⇒ UPSERT مسموح فقط حين tenant_id = المستأجِر الحاليّ.
ALTER TABLE field_state ENABLE ROW LEVEL SECURITY;
-- FORCE صراحةً: هذا الجدول يُنشأ بعد v9_rls_force_all في MANIFEST، فلا يلتقطه فرضه
-- في إقلاع نظيف ⇒ سيتجاوز مالكُ الجدول السياسةَ. نفرضه هنا (idempotent) كي يُطبَّق
-- العزل حتى على المالك فوراً. (ملاحظة مراجعة Copilot — PR #131.)
ALTER TABLE field_state FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON field_state;
CREATE POLICY tenant_isolation ON field_state
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', TRUE), ''));

CREATE INDEX IF NOT EXISTS idx_field_state_tenant ON field_state(tenant_id);
CREATE INDEX IF NOT EXISTS idx_field_state_validity ON field_state(validity);
