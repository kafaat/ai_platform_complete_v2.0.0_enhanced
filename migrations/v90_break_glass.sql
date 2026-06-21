-- ════════════════════════════════════════════════════════════
-- SAHOOL v90 — break_glass_grants: وصول عابر للمستأجرين مُدقَّق (break-glass)
-- ════════════════════════════════════════════════════════════
-- القرار الأمنيّ (بعد فصل RBAC): مدير المنصّة (platform_admin) لا يملك وصولاً
-- لبيانات المستأجِر (RLS تعزل بـapp.current_tenant). الاستثناء الوحيد المشروع هو
-- منحة break-glass صريحة: محدودة بالزمن، مُتحقّق منها بـMFA، مُعلَّلة بسبب، ومُدقَّقة
-- على كلّ استخدام. هذا الجدول هو سجلّ المنح/التدقيق — عابر للمستأجرين **بطبيعته**.
--
-- ⚠️ عزل: هذا جدول إداريّ على مستوى المنصّة (لا مُنطّق بمستأجِر واحد). لذلك:
--   • عمود الهدف اسمه target_tenant_id (وليس tenant_id) — كي لا يُفهَم كجدول
--     مُستأجَر يُعزَل بمستأجِر واحد، ولا يلتقطه حارس test_rls_tenant_coverage.
--   • نُفعّل RLS + FORCE (دفاع عمق: يُخضِع حتى مالك الجدول للسياسة).
--   • السياسة تسمح بسياق الخدمة/الإدارة فقط (مرآةً لفرع «هروب الخدمة» في
--     v87_audit_log_tenant.sql): لا مطابقة per-tenant لأنّ الجدول عابر عمداً.
--     أيّ اتّصال مُنطّق بمستأجِر (app.current_tenant مضبوط لمستأجِر) **لا** يرى
--     صفوف هذا الجدول — فلا تتسرّب المنح بين مستأجِري المنصّة.
-- idempotent بالكامل.

CREATE TABLE IF NOT EXISTS break_glass_grants (
    id               BIGSERIAL    PRIMARY KEY,
    admin_user_id    INTEGER      NOT NULL,
    admin_email      TEXT,
    target_tenant_id UUID         NOT NULL,
    reason           TEXT         NOT NULL,
    mfa_verified     BOOLEAN      NOT NULL DEFAULT FALSE,
    granted_at       TIMESTAMPTZ  DEFAULT NOW(),
    expires_at       TIMESTAMPTZ  NOT NULL,
    revoked          BOOLEAN      NOT NULL DEFAULT FALSE,
    grant_token      TEXT         UNIQUE NOT NULL,
    access_count     INTEGER      NOT NULL DEFAULT 0,
    last_used_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_break_glass_target  ON break_glass_grants(target_tenant_id);
CREATE INDEX IF NOT EXISTS idx_break_glass_admin   ON break_glass_grants(admin_user_id);
CREATE INDEX IF NOT EXISTS idx_break_glass_active  ON break_glass_grants(revoked, expires_at);

ALTER TABLE break_glass_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE break_glass_grants FORCE ROW LEVEL SECURITY;  -- يُخضِع المالك للسياسة أيضاً

-- idempotency + أسماء تاريخيّة محتملة
DROP POLICY IF EXISTS break_glass_admin_only ON break_glass_grants;
DROP POLICY IF EXISTS break_glass_policy ON break_glass_grants;

-- السياسة: سياق الخدمة/الإدارة فقط — لا مطابقة per-tenant (الجدول عابر عمداً).
-- مرآة لفرع «هروب الخدمة» في v87: سياق بلا مستأجِر (current_tenant فارغ/غير مضبوط)
-- أو دور 'admin' للخدمة. أيّ سياق مُنطّق بمستأجِر (current_tenant=مستأجِر) لا يرى/يكتب.
CREATE POLICY break_glass_policy ON break_glass_grants
    USING (
        -- سياق الخدمة/الإدارة: لا مستأجِر مضبوط ⇒ مسار إدارة المنصّة (break_glass_connection
        -- يقرأ/يكتب المنح قبل ضبط app.current_tenant على الهدف).
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        -- هروب الخدمة فقط (service-only): لا مستخدِم منصّة بشريّ يملك دور 'admin'.
        OR current_setting('app.current_role', true) = 'admin'
    )
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR current_setting('app.current_role', true) = 'admin'
    );

COMMENT ON TABLE break_glass_grants IS
    'منح break-glass: وصول مدير منصّة عابر للمستأجرين، محدود بالزمن + MFA + سبب + تدقيق على كلّ استخدام. عابر للمستأجرين عمداً (سياق إدارة/خدمة فقط).';
COMMENT ON COLUMN break_glass_grants.target_tenant_id IS
    'المستأجِر الهدف للوصول العابر — ليس tenant_id (الجدول ليس مُنطّقاً بمستأجِر واحد).';
COMMENT ON COLUMN break_glass_grants.grant_token IS
    'توكن المنحة (secrets.token_urlsafe) — يُقدَّم لاستخدام المنحة؛ فريد.';
