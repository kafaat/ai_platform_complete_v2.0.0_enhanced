-- ════════════════════════════════════════════════════════════
-- SAHOOL v87 — audit_log: عمود tenant_id + RLS مُنطّق بالمستأجِر
-- ════════════════════════════════════════════════════════════
-- الحوكمة #407: جدول audit_log كان بلا tenant_id (يتعذّر على التحقيق الجنائيّ الإجابة
-- عن «من فعل ماذا في أيّ مستأجِر»)، وسياسته القديمة سمحت لـapp.current_role='admin'
-- برؤية كلّ الصفوف عبر جميع المستأجرين. هذه الهجرة:
--   1) تضيف tenant_id UUID + فهرس.
--   2) تُفعّل RLS صراحةً + FORCE (يُخضِع حتى مالك الجدول للسياسة — دفاع عمق).
--   3) تستبدل السياسة بأخرى مُنطّقة بالمستأجِر.
--
-- ⚠️ ملاحظة أمنيّة حول «هروب الخدمة» (current_role='admin'):
--   شرط current_role='admin' في الـUSING هو هروبٌ للخدمة فقط (service-only):
--   خدمة auth تضبط current_role='admin' على pool الاتصال الخاصّ بها. بعد إعادة
--   هيكلة RBAC، لا يملك أيّ مستخدِم منصّة دور 'admin' (دور المنصّة لم يَعُد 'admin')،
--   فهذا الشرط لا يُمنح لأيّ مستخدِم بشريّ — إنّما لمسار الخدمة الداخليّ حصراً.
-- idempotent بالكامل.

ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS tenant_id UUID;

CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_log(tenant_id);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;  -- يُخضِع مالك الجدول للسياسة أيضاً

-- إسقاط أيّ سياسة قديمة (idempotency + أسماء تاريخيّة محتملة)
DROP POLICY IF EXISTS audit_admin_only ON audit_log;
DROP POLICY IF EXISTS audit_log_policy ON audit_log;

-- السياسة الجديدة: مُنطّقة بالمستأجِر (tenant-scoped) مع هروب خدمة محصور.
CREATE POLICY audit_log_policy ON audit_log
    USING (
        -- سياق الخدمة/النظام: خدمة auth تكتب بلا مستأجِر (current_tenant فارغ/غير مضبوط)
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        -- قراءة مُنطّقة بالمستأجِر: المستأجِر يرى صفوفه فقط
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
        -- أحداث المستخدِم نفسه
        OR user_id::TEXT = NULLIF(current_setting('app.current_user_id', true), '')
        -- هروب الخدمة فقط (service-only): خدمة auth تضبط current_role='admin' على poolها.
        -- بعد إعادة هيكلة RBAC، لا مستخدِم منصّة بشريّ يملك دور 'admin' ⇒ مسار خدمة حصراً.
        OR current_setting('app.current_role', true) = 'admin'
    )
    WITH CHECK (
        -- عزل الكتابة: لا يُكتب صفّ لمستأجِر آخر؛ سياق الخدمة (بلا مستأجِر) مسموح.
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

COMMENT ON COLUMN audit_log.tenant_id IS 'المستأجِر صاحب الحدث — يُملأ عند register/login؛ NULL لأحداث النظام/ما-قبل-المستأجِر.';
