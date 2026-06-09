-- ═══════════════════════════════════════════════════════════════════
-- v9_onboarding.sql — تخزين ردود استبيان دخول المزارع
-- ═══════════════════════════════════════════════════════════════════
-- المرجع: ONBOARDING_QUESTIONNAIRE.md + api/onboarding.py
-- الردود تُخزَّن كـJSONB (مرن مع تطوّر الأسئلة) + tenant_id لـRLS.

CREATE TABLE IF NOT EXISTS onboarding_responses (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     UUID NOT NULL,
    farmer_id     VARCHAR(64),
    field_id      VARCHAR(64),
    answers       JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_complete   BOOLEAN DEFAULT FALSE,   -- اكتملت الحقول الإلزاميّة؟
    answered_count INTEGER DEFAULT 0,
    version       VARCHAR(10) DEFAULT '1.0',
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_onboarding_tenant ON onboarding_responses (tenant_id);
CREATE INDEX IF NOT EXISTS idx_onboarding_field  ON onboarding_responses (field_id);

-- RLS: عزل المستأجرين (يُضاف FORCE عبر v9_rls_tenant_isolation عند تشغيله)
ALTER TABLE onboarding_responses ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS onboarding_tenant_isolation ON onboarding_responses;
CREATE POLICY onboarding_tenant_isolation ON onboarding_responses
    USING (
        -- fail-closed: بلا app.current_tenant → صفر صفوف
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    );
ALTER TABLE onboarding_responses FORCE ROW LEVEL SECURITY;
