-- ════════════════════════════════════════════════════════════
-- SAHOOL v89 — invitations: دعوات أعضاء المستأجِر (انضمام بأدوار أدنى)
-- ════════════════════════════════════════════════════════════
-- القرار التصميميّ: التسجيل الذاتيّ (register) يُنشئ **مستأجِراً جديداً معزولاً**
-- ويُسنِد 'owner'. الأعضاء الإضافيّون ينضمّون لمستأجِر **قائم** عبر **دعوة**
-- بأدوار **أدنى** (expert/farmer/viewer) — لا عبر التسجيل الذاتيّ، ولا بدور
-- owner/admin (منع تصعيد الصلاحيّات). هذا الجدول يحمل الدعوات المعلّقة/المقبولة.
--
-- ⚠️ ملاحظة أمنيّة حول RLS (نفس نمط v87_audit_log_tenant.sql):
--   هذا الجدول يُنشأ **بعد** v9_rls_force_all (الحلقة الشاملة لا تغطّيه)، فيجب أن
--   نُفعّل RLS + FORCE صراحةً (FORCE يُخضِع حتى مالك الجدول للسياسة — دفاع عمق).
--   السياسة مُنطّقة بالمستأجِر مع هروب خدمة محصور (current_role='admin' = pool خدمة
--   auth حصراً؛ لا مستخدِم منصّة بشريّ يملك دور 'admin' بعد إعادة هيكلة RBAC).
--   حارس tests_v9/test_rls_tenant_coverage.py يفرض ENABLE+FORCE+POLICY على هذا الجدول.
-- idempotent بالكامل.

CREATE TABLE IF NOT EXISTS invitations (
    id BIGSERIAL PRIMARY KEY,
    token TEXT UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    tenant_id UUID NOT NULL,
    role VARCHAR(20) NOT NULL,
    invited_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    accepted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_invitations_token ON invitations(token);
CREATE INDEX IF NOT EXISTS idx_invitations_tenant ON invitations(tenant_id);
CREATE INDEX IF NOT EXISTS idx_invitations_email ON invitations(email);

-- RLS: تفعيل صريح + FORCE (الجدول لاحق لـv9_rls_force_all ⇒ FORCE مطلوب صراحةً).
ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE invitations FORCE ROW LEVEL SECURITY;  -- يُخضِع مالك الجدول للسياسة أيضاً

-- إسقاط أيّ سياسة قديمة (idempotency).
DROP POLICY IF EXISTS invitations_tenant_isolation ON invitations;

-- السياسة: مُنطّقة بالمستأجِر مع هروب خدمة محصور (نفس نمط v87).
CREATE POLICY invitations_tenant_isolation ON invitations
    USING (
        -- سياق الخدمة/النظام: خدمة auth تقرأ بلا مستأجِر مضبوط (قبول الدعوة العموميّ
        -- يبحث بالـtoken قبل معرفة المستأجِر).
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        -- قراءة مُنطّقة بالمستأجِر: المستأجِر يرى دعواته فقط.
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
        -- هروب الخدمة فقط (service-only): pool خدمة auth يضبط current_role='admin'.
        OR current_setting('app.current_role', true) = 'admin'
    )
    WITH CHECK (
        -- عزل الكتابة: لا تُكتَب دعوة لمستأجِر آخر؛ سياق الخدمة (بلا مستأجِر) مسموح.
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
        OR current_setting('app.current_role', true) = 'admin'
    );

COMMENT ON TABLE invitations IS 'دعوات أعضاء المستأجِر — انضمام بأدوار أدنى (expert/farmer/viewer) لمستأجِر قائم؛ لا عبر التسجيل الذاتيّ.';
COMMENT ON COLUMN invitations.status IS 'pending | accepted | revoked';
COMMENT ON COLUMN invitations.role IS 'الدور المدعوّ إليه — مقيّد بـ{expert,farmer,viewer}؛ owner/admin مرفوضان (منع تصعيد).';
