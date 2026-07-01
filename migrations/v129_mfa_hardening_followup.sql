-- v129 (v29.6 line) — MFA hardening follow-up (security review fixes over v128).
-- Applied after v128. Idempotent (policies/triggers dropped+recreated).
--
-- P0 — tighten the RLS "service escape": v128 allowed ANY connection with an unset
-- app.current_tenant to read/insert (mirrored audit_log/v87). The auth pool ALWAYS sets
-- app.current_role='admin' (main.py _init_auth_conn), so we require that explicitly instead
-- of a bare tenant-null escape — no non-service connection slips through.
-- P1 — mfa_recovery_codes is service-only (no self-read of code hashes); mfa_audit_events
-- keeps tenant-scoped + self read (account-activity), and becomes append-only (no forge).

-- ── mfa_recovery_codes: service-only (role='admin'); never readable by end users ──
DROP POLICY IF EXISTS mfa_recovery_codes_policy ON mfa_recovery_codes;
CREATE POLICY mfa_recovery_codes_policy ON mfa_recovery_codes
    USING (current_setting('app.current_role', true) = 'admin')
    WITH CHECK (current_setting('app.current_role', true) = 'admin');

-- ── mfa_audit_events: service (admin) OR tenant-scoped OR own events; no bare tenant-null ──
DROP POLICY IF EXISTS mfa_audit_events_policy ON mfa_audit_events;
CREATE POLICY mfa_audit_events_policy ON mfa_audit_events
    USING (
        current_setting('app.current_role', true) = 'admin'
        OR tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
        OR user_id::TEXT = NULLIF(current_setting('app.current_user_id', true), '')
    )
    WITH CHECK (
        current_setting('app.current_role', true) = 'admin'
        OR tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    );

-- ── append-only: MFA audit trail is immutable (no UPDATE/DELETE) — reuses v9 helper ──
DROP TRIGGER IF EXISTS trg_append_only_mfa_audit_events ON mfa_audit_events;
CREATE TRIGGER trg_append_only_mfa_audit_events
    BEFORE UPDATE OR DELETE ON mfa_audit_events
    FOR EACH ROW EXECUTE FUNCTION sahool_block_mutation();
