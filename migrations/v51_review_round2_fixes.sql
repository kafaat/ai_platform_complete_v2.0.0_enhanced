-- v51: إصلاحات المراجعة النقديّة (جولة ٢) — أحداث مفقودة + عزل مستأجِر + إعادة جدولة آمنة.
--   (1) events.entity_type: إضافة 'activity' و'soil_lab_test'. كانت تُرفَض بقيد CHECK
--       ⇒ كلّ حدث نشاط/فحص تربة يُرفَض ويُبتلَع صامتاً (أحداث مفقودة لمجالين كاملين).
--   (2) RLS على lifecycle_temporal_rejections — كان جدول مستأجِر (tenant_id) بلا عزل
--       (أيّ مستأجِر يقرأ سجلّات الآخرين). نمط ::TEXT (لا يخطئ على إعداد مشوَّه).
--   (3) requeue_dead_letter/all: قصرها على مستأجِر السياق عبر ربط events. كانتا تمسّان
--       event_outbox (بلا RLS) لكلّ المستأجرين ⇒ أيّ مدقّق يعيد جدولة موتى الجميع.
-- idempotent + آمن (IF EXISTS / OR REPLACE).

-- ── (1) توسيع قيد entity_type ────────────────────────────────────
ALTER TABLE events DROP CONSTRAINT IF EXISTS events_entity_type_check;
ALTER TABLE events ADD CONSTRAINT events_entity_type_check
    CHECK (entity_type IN ('field', 'farm', 'operation', 'equipment', 'sensor', 'well',
                           'sample', 'season', 'user', 'activity', 'soil_lab_test'));

-- ── (2) RLS على lifecycle_temporal_rejections ────────────────────
ALTER TABLE lifecycle_temporal_rejections ENABLE ROW LEVEL SECURITY;
ALTER TABLE lifecycle_temporal_rejections FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON lifecycle_temporal_rejections;
CREATE POLICY tenant_isolation ON lifecycle_temporal_rejections
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', TRUE), ''));

-- ── (3) إعادة الجدولة مقصورة على مستأجِر السياق (ربط events) ──────
CREATE OR REPLACE FUNCTION requeue_dead_letter(p_outbox_id BIGINT) RETURNS BOOLEAN AS $$
DECLARE v_n INTEGER; v_tenant UUID;
BEGIN
    v_tenant := NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID;
    UPDATE event_outbox o
       SET status = 'pending', retry_count = 0, last_error = NULL
      FROM events e
     WHERE e.event_id = o.event_id
       AND o.outbox_id = p_outbox_id AND o.status = 'failed'
       AND e.tenant_id = v_tenant;   -- v_tenant NULL ⇒ لا صفوف (fail-closed)
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n > 0;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION requeue_all_dead_letter() RETURNS INTEGER AS $$
DECLARE v_n INTEGER; v_tenant UUID;
BEGIN
    v_tenant := NULLIF(current_setting('app.current_tenant', TRUE), '')::UUID;
    UPDATE event_outbox o
       SET status = 'pending', retry_count = 0, last_error = NULL
      FROM events e
     WHERE e.event_id = o.event_id AND o.status = 'failed'
       AND e.tenant_id = v_tenant;   -- مقصور على مستأجِر السياق
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END;
$$ LANGUAGE plpgsql;
