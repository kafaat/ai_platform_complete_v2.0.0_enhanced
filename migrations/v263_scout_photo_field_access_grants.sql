-- v263: P0 explicit field authorization for scouting photo and season-link APIs.
-- Renumbered from the owner delivery's v258 (v257-v261 are taken elsewhere). Owner phase 6.
-- scout-ingest-service owns the table and issues grants through its admin API
-- (owner decision 2026-11-13; the delivery had the platform as issuer). The media routes read it
-- as sahool_ingest (SELECT only); writes go through the dedicated sahool_scout_grant_admin role.
-- NO inherited access from tenant, role, pin creator, or manager.
BEGIN;
SET LOCAL lock_timeout = '15s';

-- users.id is globally unique, but composite keys are needed to make it
-- impossible to grant a user from another tenant (or cross-tenant grantor).
CREATE UNIQUE INDEX IF NOT EXISTS scout_photo_users_tenant_id_uq
  ON users (tenant_id, id);

CREATE TABLE IF NOT EXISTS scout_photo_field_access_grants (
  grant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  field_id TEXT NOT NULL,
  user_id INTEGER NOT NULL,
  scope TEXT NOT NULL CHECK (scope IN (
    'photo.read', 'photo.upload', 'photo.context', 'photo.season_link')),
  granted_by INTEGER NOT NULL,
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  revoked_by INTEGER,
  revocation_reason TEXT,
  CONSTRAINT scout_photo_grant_field_fk FOREIGN KEY (tenant_id, field_id)
    REFERENCES fields (tenant_id, field_id),
  CONSTRAINT scout_photo_grant_user_fk FOREIGN KEY (tenant_id, user_id)
    REFERENCES users (tenant_id, id),
  CONSTRAINT scout_photo_grant_issuer_fk FOREIGN KEY (tenant_id, granted_by)
    REFERENCES users (tenant_id, id),
  CONSTRAINT scout_photo_grant_revoker_fk FOREIGN KEY (tenant_id, revoked_by)
    REFERENCES users (tenant_id, id),
  CONSTRAINT scout_photo_grant_expiry_ck CHECK (
    expires_at IS NULL OR expires_at > granted_at),
  CONSTRAINT scout_photo_grant_revocation_ck CHECK (
    (revoked_at IS NULL AND revoked_by IS NULL AND revocation_reason IS NULL) OR
    (revoked_at IS NOT NULL AND revoked_by IS NOT NULL AND revocation_reason IS NOT NULL
     AND length(btrim(revocation_reason)) BETWEEN 1 AND 2000)
  )
);
-- Revoked grants remain immutable history but a fresh approved grant may be
-- issued later. Only one unrevoked grant per actor/field/scope is allowed.
CREATE UNIQUE INDEX IF NOT EXISTS scout_photo_grants_one_active_uq
  ON scout_photo_field_access_grants (tenant_id, field_id, user_id, scope)
  WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS scout_photo_grants_actor_lookup
  ON scout_photo_field_access_grants (tenant_id, user_id, scope)
  WHERE revoked_at IS NULL;

ALTER TABLE scout_photo_field_access_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE scout_photo_field_access_grants FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS scout_photo_field_access_tenant ON scout_photo_field_access_grants;
CREATE POLICY scout_photo_field_access_tenant ON scout_photo_field_access_grants
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

-- Mutations are controlled platform administration only; a revoked record is
-- never revived, and an old issuer/scope/expiry cannot be silently replaced.
CREATE OR REPLACE FUNCTION guard_scout_photo_grant_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'scout_photo_grant_deletion_forbidden' USING ERRCODE='55000';
  END IF;
  IF OLD.revoked_at IS NOT NULL OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
     OR NEW.field_id IS DISTINCT FROM OLD.field_id
     OR NEW.user_id IS DISTINCT FROM OLD.user_id
     OR NEW.scope IS DISTINCT FROM OLD.scope
     OR NEW.granted_by IS DISTINCT FROM OLD.granted_by
     OR NEW.granted_at IS DISTINCT FROM OLD.granted_at
     OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
     OR NEW.revoked_at IS NULL OR NEW.revoked_at < OLD.granted_at THEN
    RAISE EXCEPTION 'scout_photo_grant_immutable_or_invalid_revocation' USING ERRCODE='55000';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS scout_photo_grant_mutation_guard ON scout_photo_field_access_grants;
CREATE TRIGGER scout_photo_grant_mutation_guard
  BEFORE UPDATE OR DELETE ON scout_photo_field_access_grants
  FOR EACH ROW EXECUTE FUNCTION guard_scout_photo_grant_update();
REVOKE ALL ON scout_photo_field_access_grants FROM PUBLIC;
COMMENT ON TABLE scout_photo_field_access_grants IS
  'Platform-issued field and operation-scoped media grants; never inferred from RBAC.';
COMMIT;
