-- v264: platform-owned, immutable audit of field/media grant administration.
-- Renumbered from the owner delivery's v259 (v257-v261 are taken elsewhere). Owner phase 7.
-- Owner scout-ingest-service (admin API, sahool_scout_grant_admin role).
-- Only a dedicated non-BYPASSRLS DB principal may issue/revoke grants at runtime.
-- All authority checks are repeated by the authenticated platform admin router.
BEGIN;
SET LOCAL lock_timeout = '15s';

CREATE TABLE IF NOT EXISTS scout_photo_grant_audit_events (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    grant_id UUID NOT NULL,
    actor_user_id INTEGER NOT NULL,
    target_user_id INTEGER NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN (
      'photo.read', 'photo.upload', 'photo.context', 'photo.season_link')),
    action TEXT NOT NULL CHECK (action IN ('issue', 'revoke')),
    request_sha256 TEXT NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
    reason TEXT NOT NULL CHECK (length(btrim(reason)) BETWEEN 10 AND 1000),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT scout_photo_admin_audit_field_fk FOREIGN KEY (tenant_id, field_id)
      REFERENCES fields (tenant_id, field_id),
    CONSTRAINT scout_photo_admin_audit_actor_fk FOREIGN KEY (tenant_id, actor_user_id)
      REFERENCES users (tenant_id, id),
    CONSTRAINT scout_photo_admin_audit_target_fk FOREIGN KEY (tenant_id, target_user_id)
      REFERENCES users (tenant_id, id),
    -- The event is inserted first as an idempotency fence. The referenced grant
    -- must exist when the enclosing transaction commits, not beforehand.
    CONSTRAINT scout_photo_admin_audit_grant_fk FOREIGN KEY (grant_id)
      REFERENCES scout_photo_field_access_grants (grant_id)
      DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX IF NOT EXISTS scout_photo_admin_audit_tenant_field_idx
  ON scout_photo_grant_audit_events (tenant_id, field_id, recorded_at DESC);

ALTER TABLE scout_photo_grant_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE scout_photo_grant_audit_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS scout_photo_admin_audit_tenant ON scout_photo_grant_audit_events;
CREATE POLICY scout_photo_admin_audit_tenant ON scout_photo_grant_audit_events
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

CREATE OR REPLACE FUNCTION scout_photo_guard_admin_audit_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'scout_photo_admin_audit_immutable' USING ERRCODE = '55000';
END;
$$;
DROP TRIGGER IF EXISTS scout_photo_admin_audit_immutable ON scout_photo_grant_audit_events;
CREATE TRIGGER scout_photo_admin_audit_immutable
  BEFORE UPDATE OR DELETE ON scout_photo_grant_audit_events
  FOR EACH ROW EXECUTE FUNCTION scout_photo_guard_admin_audit_immutable();
REVOKE ALL ON scout_photo_grant_audit_events FROM PUBLIC;
COMMENT ON TABLE scout_photo_grant_audit_events IS
 'Append-only platform issuance/revocation events, tenant scoped; event_id is an idempotency fence.';
COMMIT;
