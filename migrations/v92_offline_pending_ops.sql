-- v92: durable pending queue for offline-first operations
-- ════════════════════════════════════════════════════════════════════════
-- المشكلة (Stage A P1): النواة sahool_core.offline_first نقيّة (لا I/O): تُدير
-- طابور العمليّات المعلّقة في **الذاكرة** فقط، فتضيع العمليّات عند إعادة تشغيل
-- العمليّة (process restart) قبل أن تُزامَن. هذا الجدول يُدِيم العمليّات لحظة
-- تسجيلها offline (status='pending')، فتنجو من إعادة التشغيل، ثمّ تُعلَّم
-- 'processed' بعد نجاح مزامنتها.
--
-- التمييز عن offline_synced_operations (v15): ذاك يُدوّن ما **اكتملت** مزامنته
-- (سجلّ نهائيّ)؛ هذا يحمل ما **ينتظر** المزامنة (طابور حيّ) مع عدّاد محاولات
-- وآخر خطأ لتتبّع التعثّر. المفتاح op_id (معرّف العميل) ⇒ الإدخال/المزامنة
-- idempotent (ON CONFLICT DO NOTHING).
--
-- العزل: RLS على tenant_id عبر الدالّة المشتركة _sahool_apply_tenant_rls
-- (مُعرّفة في v9_rls_tenant_isolation.sql، تُطبَّق قبل هذا الملف) — نفس نمط v15.
-- idempotent بالكامل (IF NOT EXISTS + DROP POLICY IF EXISTS داخل الدالّة).
CREATE TABLE IF NOT EXISTS offline_pending_ops (
    op_id        UUID PRIMARY KEY,                      -- معرّف العميل (idempotency)
    tenant_id    UUID NOT NULL,
    user_id      TEXT NOT NULL,
    op_kind      TEXT NOT NULL,                         -- OperationKind value
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    status       TEXT NOT NULL DEFAULT 'pending',       -- pending | processed
    created_at   TIMESTAMPTZ NOT NULL,                  -- حين أُنشئت offline
    processed_at TIMESTAMPTZ,                           -- حين اكتملت مزامنتها
    attempts     INTEGER NOT NULL DEFAULT 0,            -- عدّاد محاولات المزامنة
    last_error   TEXT                                   -- آخر سبب تعثّر (مُقتطَع)
);

-- فهرس استرداد الطابور: العمليّات المعلّقة لمستأجِر بترتيب FIFO (created_at ASC).
-- جزئيّ على status='pending' ⇒ خفيف ولا يتضخّم بالمُنجَزات.
CREATE INDEX IF NOT EXISTS idx_offline_pending_ops_tenant_pending
    ON offline_pending_ops (tenant_id, created_at)
    WHERE status = 'pending';

-- فهرس التنظيف (retention): حذف المُنجَزة الأقدم من عتبة.
CREATE INDEX IF NOT EXISTS idx_offline_pending_ops_processed
    ON offline_pending_ops (processed_at)
    WHERE status = 'processed';

-- RLS: تفعيل صريح + FORCE + سياسة العزل (نفس نمط v89_invitations — جدول لاحق
-- لـv9_rls_force_all/v70_propagate، فالحلقة الشاملة لا تغطّيه ⇒ يجب RLS صريحاً).
-- FORCE يُخضِع حتّى مالك الجدول للسياسة (دفاع عمق). السياسة مُنطّقة بالمستأجِر عبر
-- current_setting('app.current_tenant') (fail-closed: سياق فارغ ⇒ صفر صفوف).
ALTER TABLE offline_pending_ops ENABLE ROW LEVEL SECURITY;
ALTER TABLE offline_pending_ops FORCE ROW LEVEL SECURITY;  -- يُخضِع المالك أيضاً

DROP POLICY IF EXISTS tenant_isolation ON offline_pending_ops;  -- idempotency
CREATE POLICY tenant_isolation ON offline_pending_ops
    USING (
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    )
    WITH CHECK (
        -- عزل الكتابة (دفاع عمق): بلا سياق (هجرات/نظام) تُسمح، وإلّا المطابقة فقط.
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

COMMENT ON TABLE offline_pending_ops IS
    'طابور العمليّات المعلّقة الدائم (offline-first) — يحمل ما ينتظر المزامنة فينجو من إعادة التشغيل؛ يُكمِّل offline_synced_operations (v15) الذي يُدوّن المُكتمِل.';
