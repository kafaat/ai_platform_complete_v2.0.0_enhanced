-- SAHOOL v69 — migrations/v69_decision_policies.sql
-- سجلّ سياسات القرار: حوكمة معلنة قابلة للتهيئة لكلّ مستأجِر (المرحلة B، الشريحة 5).
--
-- الفجوة: قواعد الحوكمة (طبقات الموافقة، عتبات الماء، الحظر) مبعثرة في الكود ⇒ ضمنيّة
-- غير قابلة للتهيئة لكلّ مستأجِر/محصول/موسم. هذا الجدول يجعلها معلنة وقابلة للاستعلام:
-- لكلّ سياسة نطاقٌ (scope: action_type/risk_level/crop) وأثرٌ (effect: auto_block /
-- require_approvals / water_cap_pct) وأولويّة. تُستشار في مسار القرار الموحّد والموزِّع
-- (core/policy_registry) فتُصقَل القرارات بشفافيّة — تكمّل الحواجز، لا تستبدلها.
--
-- عزل المستأجرين إلزاميّ عبر _sahool_apply_tenant_rls (v9). idempotent بالكامل.

CREATE TABLE IF NOT EXISTS decision_policies (
    policy_id      VARCHAR(40)  PRIMARY KEY,
    tenant_id      UUID         NOT NULL,             -- عزل المستأجر (RLS أدناه)
    name           VARCHAR(120) NOT NULL,             -- اسم بشريّ للسياسة
    scope          JSONB        NOT NULL DEFAULT '{}'::jsonb,  -- متى تنطبق (None=بدل)
    effect         JSONB        NOT NULL DEFAULT '{}'::jsonb,  -- ماذا تفرض
    priority       INT          NOT NULL DEFAULT 0,   -- الأعلى يُطبَّق أوّلاً
    enabled        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by     VARCHAR(80),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- فهرس tenant_id لكفاءة مسح RLS (كلّ استعلام يُرشّح بـtenant_id).
CREATE INDEX IF NOT EXISTS idx_decision_policies_tenant ON decision_policies (tenant_id);
-- فهرس جزئيّ للسياسات المُفعّلة فقط (يُستشار منها مسار القرار الحارّ).
CREATE INDEX IF NOT EXISTS idx_decision_policies_enabled
    ON decision_policies (enabled) WHERE enabled = TRUE;

COMMENT ON TABLE  decision_policies IS
    'سجلّ سياسات القرار: حوكمة معلنة (scope→effect) لكلّ مستأجِر، تُستشار في core/policy_registry. tenant-isolated عبر RLS. v69.';
COMMENT ON COLUMN decision_policies.scope  IS 'متى تنطبق: {action_type?, risk_level?, crop?} (المفقود/None = بدل).';
COMMENT ON COLUMN decision_policies.effect IS 'ماذا تفرض: {auto_block?, require_approvals?, water_cap_pct?}.';

-- عزل المستأجرين (RLS) — تطبيق صريح إلزاميّ، محروس بوجود الدالّة المساعدة (v9):
-- ENABLE + FORCE + سياسة tenant_isolation (يُنشأ بعد v9_rls_force_all، فالـFORCE صريح هنا).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = '_sahool_apply_tenant_rls') THEN
        PERFORM _sahool_apply_tenant_rls('decision_policies');
        RAISE NOTICE 'v69: RLS مُفعّل على decision_policies';
    ELSE
        RAISE NOTICE 'v69: تخطّي تطبيق RLS الصريح — الدالّة المساعدة غير موجودة بعد (ستغطّيه v56)';
    END IF;
END $$;
