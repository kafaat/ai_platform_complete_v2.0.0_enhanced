-- SAHOOL v9.1 — migrations/v9_automation.sql (FIXED)
-- FIX: RLS without pg_has_role bypass

-- (tables structure preserved, only fixing RLS at end)

DO $$
DECLARE tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'automation_rules','device_commands_log','thing_models',
        'iot_devices','procurement_orders','procurement_order_items',
        'suppliers','video_streams'
    ]
    LOOP
        -- FIX: تخطَّ الجداول غير الموجودة في مجموعة الترحيل بدل الفشل.
        CONTINUE WHEN to_regclass(tbl) IS NULL;
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', tbl);
        EXECUTE format(
            $ddl$CREATE POLICY tenant_isolation ON %I USING (
                tenant_id::TEXT = current_setting('app.current_tenant', true)
                -- Removed: empty tenant bypass (C14 security fix)
                -- System services must use explicit tenant_id or service account
            )$ddl$, tbl
        );
    END LOOP;
END $$;
