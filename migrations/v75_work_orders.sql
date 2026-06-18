-- migrations/v75_work_orders.sql
--
-- نظام تنفيذ عمليّات المزرعة (FOES) — البِدئة (primitive) الأساس: أمر العمل work_orders.
-- يحوّل التوصية إلى عمل زراعيّ قابل للتنفيذ والتتبّع (ريّ/تسميد/رشّ/استكشاف/حصاد) عبر
-- آلة حالات (راجع core/work_order.py): planned→assigned→in_progress→done→verified،
-- مع cancelled كمسار إلغاء، وإعادة عمل done→in_progress.
--
--   • field_id نصّ (TEXT) لا UUID — يطابق fields.field_id VARCHAR(50) (راجع v18/v74).
--   • tenant_id UUID NOT NULL ⇒ عزل المستأجِر عبر RLS+FORCE بسياسة current_setting
--     (تطابق حُرّاس test_rls_*؛ الكتابة عبر sahool_app NOBYPASSRLS لا superuser).
--   • قيود CHECK على wo_type وstatus لمنع القيم خارج آلة الحالات على مستوى التخزين.
-- idempotent (CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS قبل CREATE POLICY).

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS work_orders (
    work_order_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL,
    field_id          TEXT NOT NULL,
    wo_type           TEXT NOT NULL CHECK (
                          wo_type IN ('irrigation', 'fertilization', 'spraying', 'scouting', 'harvest')
                      ),
    status            TEXT NOT NULL DEFAULT 'planned' CHECK (
                          status IN ('planned', 'assigned', 'in_progress', 'done', 'verified', 'cancelled')
                      ),
    recommendation_id TEXT,
    assigned_to       TEXT,
    due_at            TIMESTAMPTZ,
    payload           JSONB,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_wo_tenant_status ON work_orders(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_wo_field ON work_orders(field_id);

-- ── RLS+FORCE + سياسة tenant_isolation (current_setting — تطابق الحُرّاس) ──
ALTER TABLE work_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE work_orders FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON work_orders;
CREATE POLICY tenant_isolation ON work_orders
USING (
    tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR tenant_id::TEXT = current_setting('app.current_tenant', true)
);

COMMIT;
