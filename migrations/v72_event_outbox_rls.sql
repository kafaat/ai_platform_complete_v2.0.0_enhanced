-- migrations/v72_event_outbox_rls.sql
--
-- HIGH-002 (شهادة الإنتاج): event_outbox بلا RLS ⇒ sahool_app يقرأ/يكتب صفوف كلّ
-- المستأجرين. لا عمود tenant_id فيه (يُعزَل عبر event_id → events). استعلام تطبيق
-- مباشر عليه يكشف صفوف غيره.
--
-- يُمكَّن الآن لأنّ المرسِل (OutboxWorker: event_outbox→NATS) صار يستعمل مسبح
-- المهامّ (دور sahool_jobs، BYPASSRLS) عبر JOBS_DATABASE_URL — فيقرأ المعلّق عابراً
-- للمستأجرين كما يتطلّب نمط outbox، بينما يبقى **التطبيق** (sahool_app) معزولاً.
--
-- emit_event يكتب صفّ outbox فور كتابة الحدث في نفس الدالّة تحت سياق المستأجِر ⇒
-- WITH CHECK يمرّ (الحدث موجود لذلك المستأجِر). كتابة النظام بلا سياق مسموحة كذلك.

BEGIN;

ALTER TABLE event_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_outbox FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON event_outbox;

CREATE POLICY tenant_isolation ON event_outbox
USING (
    EXISTS (
        SELECT 1 FROM events e
        WHERE e.event_id = event_outbox.event_id
          AND e.tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    )
)
WITH CHECK (
    NULLIF(current_setting('app.current_tenant', true), '') IS NULL
    OR EXISTS (
        SELECT 1 FROM events e
        WHERE e.event_id = event_outbox.event_id
          AND e.tenant_id::TEXT = current_setting('app.current_tenant', true)
    )
);

COMMIT;
