-- v194: FII Safety Increment 1B (batch 2) — fail-closed tenant RLS
-- for the existing chemical-intervention decision/execution lineage chain.
--
-- Scope is deliberately limited to existing SoR tables that may participate in:
-- recommendation -> decision -> work order -> actuator dedup -> outcome -> lineage.
-- Missing, empty, malformed, or wrong app.current_tenant must never authorize writes.
--
-- Fail-closed contract (forensic finding #12): every table in required_tables is REQUIRED
-- by this point in the migration chain (created by v75-v82) and carries FII-critical
-- decision/execution lineage. Silently skipping a missing one — the previous
-- `IF to_regclass(...) IS NOT NULL THEN` behavior — would leave that table writable without
-- tenant isolation, a fail-OPEN gap. So a missing required table is a hard error. Only
-- genuinely-deferred future chain tables belong in optional_tables (guard-and-skip); it is
-- empty today, and keeping the two lists explicit makes the coverage contract auditable.

DO $$
DECLARE
    required_tables text[] := ARRAY[
        'recommendations',        -- v77
        'decision_record',        -- v78
        'work_orders',            -- v75
        'actuator_command_dedup', -- v81
        'outcome_record',         -- v79
        'lineage_link'            -- v82
    ];
    optional_tables text[] := ARRAY[]::text[];  -- genuinely-deferred future chain tables
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY required_tables || optional_tables
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
        ELSIF table_name = ANY(optional_tables) THEN
            RAISE NOTICE 'v194 FII: optional chain table public.% absent — skipped.', table_name;
        ELSE
            RAISE EXCEPTION 'v194 FII fail-closed: required chain table public.% is absent; refusing to leave an FII chemical-lineage write path unprotected (check migration ordering — v75-v82 must run first).', table_name;
        END IF;
    END LOOP;
END $$;
