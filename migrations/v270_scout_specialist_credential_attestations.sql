-- v270: Tenant-owner attested professional registration check, not a live issuer integration.
-- Renumbered from the owner delivery's v265 (v257-v261 are taken elsewhere). Owner phase 11.
-- Tenant owner = users.role 'owner' or 'admin' (the platform's OWNER aliases,
-- api/main.py:_ROLE_ALIASES); the delivery accepted 'owner' only.
-- Independent owner may record issuer-registry evidence; the specialist cannot self-verify.
BEGIN;
SET LOCAL lock_timeout='15s';
CREATE TABLE IF NOT EXISTS scout_specialist_credential_events (
 event_id UUID PRIMARY KEY,
 tenant_id UUID NOT NULL,
 subject_user_id INTEGER NOT NULL,
 actor_user_id INTEGER NOT NULL,
 action TEXT NOT NULL CHECK(action IN ('attest_registry_check','revoke')),
 discipline TEXT NOT NULL CHECK(discipline IN ('plant_pathology','crop_protection','agronomy')),
 issuer_code TEXT,
 jurisdiction TEXT,
 license_sha256 CHAR(64),
 registry_check_ref TEXT,
 expires_at TIMESTAMPTZ,
 previous_event_id UUID,
 reason TEXT NOT NULL CHECK(length(btrim(reason)) BETWEEN 20 AND 2000),
 recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CONSTRAINT scout_credentials_subject_fk FOREIGN KEY(tenant_id,subject_user_id) REFERENCES users(tenant_id,id),
 CONSTRAINT scout_credentials_actor_fk FOREIGN KEY(tenant_id,actor_user_id) REFERENCES users(tenant_id,id),
 CONSTRAINT scout_credentials_chain_scope_uq UNIQUE(event_id,tenant_id,subject_user_id,discipline),
 CONSTRAINT scout_credentials_prev_fk FOREIGN KEY(previous_event_id,tenant_id,subject_user_id,discipline)
  REFERENCES scout_specialist_credential_events(event_id,tenant_id,subject_user_id,discipline),
 CONSTRAINT scout_credentials_successor_uq UNIQUE(previous_event_id),
 CONSTRAINT scout_credentials_shape CHECK (
   (action='attest_registry_check' AND issuer_code IS NOT NULL AND length(btrim(issuer_code)) BETWEEN 2 AND 100
    AND jurisdiction IS NOT NULL AND length(btrim(jurisdiction)) BETWEEN 2 AND 100
    AND license_sha256 IS NOT NULL AND license_sha256 ~ '^[a-f0-9]{64}$'
    AND registry_check_ref IS NOT NULL AND length(btrim(registry_check_ref)) BETWEEN 12 AND 300
    AND expires_at IS NOT NULL)
   OR (action='revoke' AND previous_event_id IS NOT NULL AND issuer_code IS NULL AND jurisdiction IS NULL
     AND license_sha256 IS NULL AND registry_check_ref IS NULL AND expires_at IS NULL)),
 CONSTRAINT scout_credentials_no_self CHECK(actor_user_id<>subject_user_id),
 CONSTRAINT scout_credentials_no_self_reference CHECK(previous_event_id IS NULL OR previous_event_id<>event_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS scout_credentials_root_uq ON scout_specialist_credential_events
 (tenant_id,subject_user_id,discipline) WHERE previous_event_id IS NULL;
CREATE INDEX IF NOT EXISTS scout_credentials_history_idx ON scout_specialist_credential_events
 (tenant_id,subject_user_id,discipline,recorded_at DESC);
ALTER TABLE scout_specialist_credential_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE scout_specialist_credential_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS scout_credentials_tenant ON scout_specialist_credential_events;
CREATE POLICY scout_credentials_tenant ON scout_specialist_credential_events
 USING (tenant_id::text=NULLIF(current_setting('app.current_tenant',true),''))
 WITH CHECK (tenant_id::text=NULLIF(current_setting('app.current_tenant',true),''));
CREATE OR REPLACE FUNCTION scout_credentials_guard() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE prev_action TEXT;
BEGIN
 IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'scout_credentials_immutable' USING ERRCODE='55000'; END IF;
 IF NOT EXISTS(SELECT 1 FROM users u WHERE u.tenant_id=NEW.tenant_id AND u.id=NEW.actor_user_id
   AND u.active IS TRUE AND lower(u.role::text) IN ('owner','admin')) THEN
   RAISE EXCEPTION 'scout_credentials_owner_required' USING ERRCODE='42501';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM users u WHERE u.tenant_id=NEW.tenant_id AND u.id=NEW.subject_user_id
   AND u.active IS TRUE AND lower(u.role::text) IN ('expert','agronomist')) THEN
   RAISE EXCEPTION 'scout_credentials_subject_not_eligible' USING ERRCODE='42501';
 END IF;
 IF NEW.previous_event_id IS NOT NULL THEN
    SELECT action INTO prev_action FROM scout_specialist_credential_events
      WHERE event_id=NEW.previous_event_id AND tenant_id=NEW.tenant_id AND subject_user_id=NEW.subject_user_id;
    IF prev_action IS NULL OR (NEW.action='revoke' AND prev_action<>'attest_registry_check') THEN
      RAISE EXCEPTION 'scout_credentials_invalid_predecessor' USING ERRCODE='23514'; END IF;
 ELSIF NEW.action='revoke' THEN
    RAISE EXCEPTION 'scout_credentials_revoke_requires_predecessor' USING ERRCODE='23514';
 END IF;
 IF NEW.action='attest_registry_check' AND (NEW.expires_at<=now() OR NEW.expires_at>now()+interval '3 years') THEN
    RAISE EXCEPTION 'scout_credentials_expiry_invalid' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$;
DROP TRIGGER IF EXISTS scout_credentials_event_guard ON scout_specialist_credential_events;
CREATE TRIGGER scout_credentials_event_guard BEFORE INSERT OR UPDATE OR DELETE ON scout_specialist_credential_events
 FOR EACH ROW EXECUTE FUNCTION scout_credentials_guard();
REVOKE ALL ON scout_specialist_credential_events FROM PUBLIC;
COMMENT ON TABLE scout_specialist_credential_events IS
 'Owner-recorded manual issuer-registry check. Not cryptographically issuer verified; no pesticide authority.';
-- A professional photo review is never accepted solely on a JWT role or field grant.
-- Owner attestation is a *manual registry check*, not independent issuer proof.
CREATE OR REPLACE FUNCTION scout_review_credential_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
 IF TG_OP='INSERT' AND NEW.action='review' AND NOT EXISTS (
   SELECT 1 FROM scout_specialist_credential_events c
   JOIN users owner ON owner.tenant_id=c.tenant_id AND owner.id=c.actor_user_id
   WHERE c.tenant_id=NEW.tenant_id AND c.subject_user_id=NEW.reviewer_user_id
     AND c.discipline IN ('plant_pathology','agronomy')
     AND c.action='attest_registry_check' AND c.expires_at>now()
     AND owner.active IS TRUE AND lower(owner.role::text) IN ('owner','admin')
     AND NOT EXISTS (SELECT 1 FROM scout_specialist_credential_events n WHERE n.previous_event_id=c.event_id)
 ) THEN
   RAISE EXCEPTION 'scout_review_active_professional_credential_required' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END; $$;
DROP TRIGGER IF EXISTS scout_review_credential_required ON scout_photo_human_review_events;
CREATE TRIGGER scout_review_credential_required BEFORE INSERT ON scout_photo_human_review_events
 FOR EACH ROW EXECUTE FUNCTION scout_review_credential_guard();
COMMIT;
