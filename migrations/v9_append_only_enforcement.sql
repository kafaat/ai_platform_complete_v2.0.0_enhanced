-- ═══════════════════════════════════════════════════════════════════
-- v9_append_only_enforcement.sql — إنفاذ immutability فعليّاً (مراجعة #6د)
-- ═══════════════════════════════════════════════════════════════════
-- المشكلة: events + field_lifecycle_transitions + audit موصوفة "immutable"
-- في التعليقات، لكن لا شيء يمنع UPDATE/DELETE فعليّاً. دور تطبيق مخترق
-- يستطيع تزوير التاريخ. هذا يفرض append-only على مستوى DB (trigger).

CREATE OR REPLACE FUNCTION sahool_block_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'الجدول % append-only — UPDATE/DELETE ممنوع (immutable audit)',
        TG_TABLE_NAME
        USING ERRCODE = 'check_violation';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- طبّق على الجداول الـappend-only (events + سجلّ الانتقالات + الرفض الزمني)
DO $$
DECLARE
    t TEXT;
    tables TEXT[] := ARRAY['events', 'field_lifecycle_transitions',
                           'lifecycle_temporal_rejections', 'audit_log'];
BEGIN
    FOREACH t IN ARRAY tables LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = t AND table_schema = 'public') THEN
            EXECUTE format(
                'DROP TRIGGER IF EXISTS trg_append_only_%I ON %I', t, t);
            EXECUTE format(
                'CREATE TRIGGER trg_append_only_%I BEFORE UPDATE OR DELETE ON %I '
                'FOR EACH ROW EXECUTE FUNCTION sahool_block_mutation()', t, t);
        END IF;
    END LOOP;
END $$;

-- ملاحظة: INSERT يبقى مسموحاً (append). فقط UPDATE/DELETE محظوران.
-- التصحيحات تتمّ بحدث جديد (compensating event)، لا بتعديل القديم.
