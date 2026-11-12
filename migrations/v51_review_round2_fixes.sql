-- v51: إصلاحات المراجعة النقديّة (جولة ٢) — أحداث مفقودة + عزل مستأجِر + إعادة جدولة آمنة.
--   (1) events.entity_type: إضافة 'activity' و'soil_lab_test'. كانت تُرفَض بقيد CHECK
--       ⇒ كلّ حدث نشاط/فحص تربة يُرفَض ويُبتلَع صامتاً (أحداث مفقودة لمجالين كاملين).
--   (2) RLS على lifecycle_temporal_rejections — كان جدول مستأجِر (tenant_id) بلا عزل
--       (أيّ مستأجِر يقرأ سجلّات الآخرين). نمط ::TEXT (لا يخطئ على إعداد مشوَّه).
--   (3) requeue_dead_letter/all: قصرها على مستأجِر السياق عبر ربط events. كانتا تمسّان
--       event_outbox (بلا RLS) لكلّ المستأجرين ⇒ أيّ مدقّق يعيد جدولة موتى الجميع.
-- idempotent + آمن (IF EXISTS / OR REPLACE).

-- ── (1) توسيع قيد entity_type ────────────────────────────────────
-- events.entity_type accepts every entity category the platform emits.
--
-- This CHECK first held 11 values (v11, then this file), while the platform emits 34:
-- harvest lots, tasks, alerts, calibration overrides, decision records, irrigation plans
-- and more. The database rejected each of those events. Non-critical emits logged and
-- swallowed the failure, so the event never existed; critical ones (HARVEST_LOT_CREATED,
-- CUSTODY_EVENT_RECORDED, YIELD_MAP_INGESTED, CALIBRATION_OVERRIDE_SET) aborted the
-- business write. The list lives here, not in a new file, because MANIFEST.txt and
-- scripts_v9/run_migrations.sql are GATE-01 frozen paths.
--
-- The value set is ALLOWED_ENTITY_TYPES in services/sahool-platform/core/event_schema.py;
-- tests_v9/test_events_entity_type_contract.py fails if the two drift or if a call site
-- emits a value outside it.
--
-- Re-run safety (MANIFEST is re-applied on every deploy): the constraint is replaced only
-- when it does not already accept every value below, so a re-run neither rescans events
-- nor narrows a later, wider constraint (the old unconditional DROP+ADD narrowed it back
-- and failed once any row held a newer category). It is added NOT VALID: every new row is
-- checked at once, and no existing row can violate it (each one passed a narrower set).
-- VALIDATE CONSTRAINT is an operator step (docs/runbooks/validate_not_valid_constraints.md).
DO $v51$
DECLARE
    wanted text[] := ARRAY[
        'activity',
        'alert',
        'calibration_audit',
        'calibration_override',
        'crop_rotation',
        'decision_record',
        'dispatch_decision',
        'equipment',
        'equipment_maintenance',
        'farm',
        'field',
        'harvest_lot',
        'inventory_batch',
        'inventory_item',
        'irrigation_execution_plan',
        'irrigation_manual_execution',
        'irrigation_schedule',
        'irrigation_valve',
        'lineage_link',
        'master_data',
        'notification_delivery',
        'operation',
        'outcome_record',
        'recommendation',
        'sample',
        'season',
        'sensor',
        'soil_lab_test',
        'task',
        'tenant',
        'user',
        'well',
        'work_order',
        'yield_map_ingestion'
    ];
    have text;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO have
    FROM pg_constraint
    WHERE conrelid = 'events'::regclass AND conname = 'events_entity_type_check';

    IF have IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM unnest(wanted) AS w(v) WHERE have NOT LIKE '%''' || w.v || '''%'
    ) THEN
        RETURN;
    END IF;

    ALTER TABLE events DROP CONSTRAINT IF EXISTS events_entity_type_check;
    -- An IN list (not ANY of one array literal) so pg_get_constraintdef renders each value
    -- quoted ('harvest_lot'::text): the membership tests above and in v51 read it that way.
    EXECUTE format(
        'ALTER TABLE events ADD CONSTRAINT events_entity_type_check '
        'CHECK (entity_type IN (%s)) NOT VALID',
        (SELECT string_agg(quote_literal(v), ', ' ORDER BY v) FROM unnest(wanted) AS w(v))
    );
END
$v51$;

-- ── (2) RLS على lifecycle_temporal_rejections ────────────────────
ALTER TABLE lifecycle_temporal_rejections ENABLE ROW LEVEL SECURITY;
-- FORCE صراحةً: يُنشأ هذا الجدول بعد v9_rls_force_all في MANIFEST فلا يلتقطه
-- فرضُه في إقلاع نظيف (حاوية بإقلاع واحد) ⇒ يتجاوز المالكُ العزلَ. idempotent.
ALTER TABLE lifecycle_temporal_rejections FORCE ROW LEVEL SECURITY;
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
