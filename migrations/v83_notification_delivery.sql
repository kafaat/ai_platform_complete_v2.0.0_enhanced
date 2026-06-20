-- migrations/v83_notification_delivery.sql
--
-- إيصالات تسليم الإشعار (Notification Delivery Receipts) — إغلاق دورة الإشعار: حتى
-- الآن تُحسب القنوات وتُسلَّم لكن لا أثر **مُدام** لحالة كلّ تسليم (queued/sent/failed/
-- delivered) لكلّ تنبيه×قناة، فلا تدقيق ولا إعادة محاولة ولا «هل وصل؟». هذا الجدول
-- يُدِيم إيصالاً لكلّ (مستأجِر، مفتاح تنبيه، قناة) ويُحدّثه عبر دورة الحياة.
--
--   • UNIQUE(tenant_id, alert_key, channel) ⇒ إيصال واحد لكلّ تنبيه×قناة (upsert).
--   • status CHECK ضمن مجموعة مغلقة (queued|sent|failed|delivered) — لا حالة مُلفّقة.
--   • error TEXT: سبب الفشل (provenance للتشخيص) — NULL عند النجاح.
--   • tenant_id UUID NOT NULL ⇒ عزل المستأجِر عبر RLS+FORCE بسياسة current_setting.
--   • فهرس (tenant_id, alert_key) لجلب كلّ قنوات تنبيه واحد بكفاءة.
-- idempotent (CREATE TABLE IF NOT EXISTS + DROP POLICY IF EXISTS قبل CREATE POLICY).

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS notification_delivery (
    delivery_id  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID         NOT NULL,                 -- عزل المستأجِر (RLS أدناه)
    alert_key    TEXT         NOT NULL,                 -- مفتاح التنبيه (field:code:severity)
    channel      TEXT         NOT NULL,                 -- قناة التسليم (log/in_app/webhook/sms/whatsapp/…)
    status       TEXT         NOT NULL DEFAULT 'queued' -- دورة حياة التسليم (مجموعة مغلقة)
        CHECK (status IN ('queued', 'sent', 'failed', 'delivered')),
    error        TEXT,                                  -- سبب الفشل (NULL عند النجاح)
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, alert_key, channel)              -- إيصال واحد لكلّ تنبيه×قناة (upsert)
);

-- جلب كلّ قنوات تنبيه واحد لمستأجِر بكفاءة (تتبّع «هل وصل عبر كلّ قناة؟»).
CREATE INDEX IF NOT EXISTS idx_notification_delivery_alert
    ON notification_delivery (tenant_id, alert_key);

COMMENT ON TABLE  notification_delivery IS
    'إيصالات تسليم الإشعار لكلّ مستأجِر×تنبيه×قناة (إغلاق دورة الإشعار). tenant-isolated عبر RLS. v83.';
COMMENT ON COLUMN notification_delivery.alert_key IS 'مفتاح التنبيه (field_id:code:severity) — مرآة _alert_key في core.alert_delivery.';
COMMENT ON COLUMN notification_delivery.status    IS 'دورة حياة التسليم: queued|sent|failed|delivered (مجموعة مغلقة، لا حالة مُلفّقة).';
COMMENT ON COLUMN notification_delivery.error     IS 'سبب الفشل (provenance للتشخيص) — NULL عند النجاح.';

-- ── RLS+FORCE + سياسة tenant_isolation (current_setting — تطابق الحُرّاس) ──
ALTER TABLE notification_delivery ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_delivery FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON notification_delivery;
CREATE POLICY tenant_isolation ON notification_delivery
USING (
    tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR tenant_id::TEXT = current_setting('app.current_tenant', true)
);

COMMIT;
