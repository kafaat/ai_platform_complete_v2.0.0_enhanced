-- v194: FII Safety Increment 1B (batch 2) — fail-closed tenant RLS
-- for the existing chemical-intervention decision/execution lineage chain.
--
-- Scope is deliberately limited to existing SoR tables that may participate in:
-- recommendation -> decision -> work order -> actuator dedup -> outcome -> lineage.
-- Missing, empty, malformed, or wrong app.current_tenant must never authorize writes.

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'recommendations',
        'decision_record',
        'work_orders',
        'actuator_command_dedup',
        'outcome_record',
        'lineage_link'
    ]
    LOOP
        IF to_regclass('public.' || table_name) IS NOT NULL THEN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
            EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', table_name);
            EXECUTE format(
                'CREATE POLICY tenant_isolation ON %I '
                'USING (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), '''')) '
                'WITH CHECK (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), ''''))',
                table_name
            );
        END IF;
    END LOOP;
END $$;
