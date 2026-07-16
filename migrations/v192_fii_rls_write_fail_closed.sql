-- v192: FII Safety Increment 1B — fail-closed tenant write policies.
-- Scope intentionally limited to the first FII-critical tables:
--   * scouting_pins
--   * prescriptions
--
-- Runtime writes MUST carry app.current_tenant. Migrations and privileged maintenance
-- use the dedicated migration/schema-owner roles; they are not exempted in app policy.

DO $$
BEGIN
    IF to_regclass('public.scouting_pins') IS NOT NULL THEN
        ALTER TABLE scouting_pins ENABLE ROW LEVEL SECURITY;
        ALTER TABLE scouting_pins FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS tenant_isolation ON scouting_pins;
        CREATE POLICY tenant_isolation ON scouting_pins
            USING (
                tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')
            )
            WITH CHECK (
                tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')
            );
    END IF;

    IF to_regclass('public.prescriptions') IS NOT NULL THEN
        ALTER TABLE prescriptions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE prescriptions FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS tenant_isolation ON prescriptions;
        CREATE POLICY tenant_isolation ON prescriptions
            USING (
                tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')
            )
            WITH CHECK (
                tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')
            );
    END IF;
END $$;

COMMENT ON POLICY tenant_isolation ON scouting_pins IS
    'FII safety: fail-closed read/write isolation; missing, empty, malformed, or wrong tenant context cannot write.';
COMMENT ON POLICY tenant_isolation ON prescriptions IS
    'FII safety: fail-closed read/write isolation; missing, empty, malformed, or wrong tenant context cannot write.';
