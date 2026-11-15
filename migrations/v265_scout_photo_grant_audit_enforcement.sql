-- v265: fail closed at COMMIT, even if the dedicated admin DB credential is
-- Renumbered from the owner delivery's v260 (v257-v261 are taken elsewhere). Owner phase 7.
-- used outside the platform API. Historical v263 grants are not rewritten.
-- A new issue/revoke must have one matching immutable audit event in the
-- same committed transaction; no new perpetual media-field grants.
BEGIN;
SET LOCAL lock_timeout = '15s';

CREATE UNIQUE INDEX IF NOT EXISTS scout_photo_grant_one_issue_event_uq
    ON scout_photo_grant_audit_events (grant_id) WHERE action = 'issue';
CREATE UNIQUE INDEX IF NOT EXISTS scout_photo_grant_one_revoke_event_uq
    ON scout_photo_grant_audit_events (grant_id) WHERE action = 'revoke';

CREATE OR REPLACE FUNCTION scout_photo_enforce_grant_audit_at_commit() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- No unbounded or backdated access in newly issued grants. Existing
        -- grants pre-dating v265 remain unchanged until naturally revoked.
        IF NEW.expires_at IS NULL OR NEW.expires_at <= NEW.granted_at OR
           NEW.expires_at > NEW.granted_at + interval '90 days' THEN
            RAISE EXCEPTION 'scout_photo_grant_expiry_policy_violation'
                USING ERRCODE = '23514';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM scout_photo_grant_audit_events e
            WHERE e.grant_id = NEW.grant_id AND e.tenant_id = NEW.tenant_id
              AND e.field_id = NEW.field_id AND e.actor_user_id = NEW.granted_by
              AND e.target_user_id = NEW.user_id AND e.scope = NEW.scope
              AND e.action = 'issue'
        ) THEN
            RAISE EXCEPTION 'scout_photo_grant_missing_issuance_audit'
                USING ERRCODE = '23514';
        END IF;
    ELSIF TG_OP = 'UPDATE' AND OLD.revoked_at IS NULL AND NEW.revoked_at IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM scout_photo_grant_audit_events e
            WHERE e.grant_id = NEW.grant_id AND e.tenant_id = NEW.tenant_id
              AND e.field_id = NEW.field_id AND e.actor_user_id = NEW.revoked_by
              AND e.target_user_id = NEW.user_id AND e.scope = NEW.scope
              AND e.action = 'revoke' AND e.reason = NEW.revocation_reason
        ) THEN
            RAISE EXCEPTION 'scout_photo_grant_missing_revocation_audit'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS scout_photo_grant_require_audit ON scout_photo_field_access_grants;
CREATE CONSTRAINT TRIGGER scout_photo_grant_require_audit
    AFTER INSERT OR UPDATE ON scout_photo_field_access_grants
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION scout_photo_enforce_grant_audit_at_commit();
COMMIT;
