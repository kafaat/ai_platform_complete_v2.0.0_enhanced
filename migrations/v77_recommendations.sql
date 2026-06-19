-- migrations/v77_recommendations.sql
--
-- تخزين + تدقيق التوصية (C1/C2 في تقرير الفجوات): كانت التوصية تُولَّد ثمّ rec_id
-- عابر في الذاكرة يُعاد في JSON ويُفقَد — بلا جدول، بلا حدث تدقيق، بلا ربط شرح.
-- هذا الجدول يحفظ كلّ توصية مُولَّدة (مُسلَّمة أو مرفوضة) مع شرحها الكامل (provenance:
-- نسخ النماذج + مصدر الطقس + لقطة المدخلات، و cross_reference: الحالات التاريخيّة
-- المشابهة) ⇒ تصبح التوصية متتبَّعة/مدقَّقة، ويُجلب شرحها لاحقاً بـrec_id.
--
--   • PK بديل UUID + rec_id نصّ مفهرس (لا UNIQUE): rec_id بدقّة ثانية
--     (rec_{tenant}_{YYYYMMDD_HHMMSS}) قد يتكرّر ⇒ نتجنّب فشل الإدراج، والجلب يُعيد الأحدث.
--   • tenant_id UUID NOT NULL ⇒ عزل المستأجِر عبر RLS+FORCE بسياسة current_setting
--     (تطابق حُرّاس test_rls_*؛ الكتابة عبر sahool_app NOBYPASSRLS لا superuser).
--   • field_id/farm_id/crop نصّ (يطابق fields.field_id VARCHAR — راجع v18/v74/v75/v76).
--   • recommendation/cross_reference/provenance حقول JSONB (قد تكون {} لتوصية مرفوضة).
--   • يُصدِر مساره حدث RECOMMENDATION_CREATED عبر outbox (event_bus) ضمن نفس المعاملة.
-- idempotent (CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS قبل CREATE POLICY).

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS recommendations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rec_id          TEXT NOT NULL,
    tenant_id       UUID NOT NULL,
    farm_id         TEXT,
    field_id        TEXT,
    crop            TEXT,
    delivered       BOOLEAN NOT NULL DEFAULT FALSE,
    reason_ar       TEXT,
    recommendation  JSONB,   -- base_recommendation (محتوى التوصية)
    cross_reference JSONB,   -- حالات تاريخيّة مشابهة (جزء من الشرح)
    provenance      JSONB,   -- model_versions + weather + snapshot (الشرح/forensic)
    issued_at       TIMESTAMPTZ,  -- result.timestamp (لحظة التوليد)
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_recommendations_rec_id ON recommendations(tenant_id, rec_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_field ON recommendations(tenant_id, field_id);

-- ── RLS+FORCE + سياسة tenant_isolation (current_setting — تطابق الحُرّاس) ──
ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON recommendations;
CREATE POLICY tenant_isolation ON recommendations
USING (
    tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR tenant_id::TEXT = current_setting('app.current_tenant', true)
);

COMMIT;
