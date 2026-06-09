-- تراجع v9_rls_tenant_isolation: يزيل FORCE RLS + السياسات.
-- ⚠ تحذير: التراجع يُلغي عزل المستأجرين — لا تشغّله في إنتاج حيّ بمستأجرين.
DO $$
DECLARE t TEXT;
  tables TEXT[] := ARRAY['fields','field_lifecycle_transitions','field_tasks',
    'agent_queries','market_sales_listings','soil_readings',
    'imagery_automation_fields','commands','field_lifecycle','events',
    'trueup_calibrations','sharing_keys','onboarding_responses'];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name=t AND table_schema='public') THEN
      EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', t);
      EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', t);
      EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    END IF;
  END LOOP;
END $$;
