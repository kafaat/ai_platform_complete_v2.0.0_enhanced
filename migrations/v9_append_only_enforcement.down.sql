-- تراجع v9_append_only_enforcement: يزيل triggers منع UPDATE/DELETE.
-- ⚠ التراجع يجعل جداول التدقيق قابلة للتعديل — لا يُنصح في إنتاج.
DO $$
DECLARE t TEXT;
  tables TEXT[] := ARRAY['events','field_lifecycle_transitions',
    'lifecycle_temporal_rejections','audit_log'];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name=t AND table_schema='public') THEN
      EXECUTE format('DROP TRIGGER IF EXISTS trg_append_only_%I ON %I', t, t);
    END IF;
  END LOOP;
END $$;
DROP FUNCTION IF EXISTS sahool_block_mutation();
