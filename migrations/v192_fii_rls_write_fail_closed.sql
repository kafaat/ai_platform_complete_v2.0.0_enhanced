-- v192: FII Safety Increment 1B — fail-closed tenant write policies.
-- Scope intentionally limited to the first FII-critical tables:
--   * scouting_pins   (created by v94)
--   * prescriptions   (created by v95)
--
-- Runtime writes MUST carry app.current_tenant. Migrations and privileged maintenance
-- use the dedicated migration/schema-owner roles; they are not exempted in app policy.
--
-- Fail-closed contract (forensic finding #11): both tables are REQUIRED by this point in
-- the migration chain. Their absence is schema drift that would silently leave an
-- FII-critical write path unprotected, so it is a hard error — NOT a silent skip. The
-- policy COMMENT is applied inside the same guaranteed-existence block, so a partial
-- schema can never reach an unguarded COMMENT ON POLICY on a non-existent policy.

DO $$
BEGIN
    -- scouting_pins (created by v94) — REQUIRED; absence is fail-closed schema drift.
    IF to_regclass('public.scouting_pins') IS NULL THEN
        RAISE EXCEPTION 'v192 FII fail-closed: required table public.scouting_pins is absent; refusing to leave an FII-critical write path unprotected (check migration ordering — v94 must run first).';
    END IF;
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
    COMMENT ON POLICY tenant_isolation ON scouting_pins IS
        'FII safety: fail-closed read/write isolation; missing, empty, malformed, or wrong tenant context cannot write.';

    -- prescriptions (created by v95) — REQUIRED; absence is fail-closed schema drift.
    IF to_regclass('public.prescriptions') IS NULL THEN
        RAISE EXCEPTION 'v192 FII fail-closed: required table public.prescriptions is absent; refusing to leave an FII-critical write path unprotected (check migration ordering — v95 must run first).';
    END IF;
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
    COMMENT ON POLICY tenant_isolation ON prescriptions IS
        'FII safety: fail-closed read/write isolation; missing, empty, malformed, or wrong tenant context cannot write.';
END $$;
