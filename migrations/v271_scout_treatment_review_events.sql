-- v271: Human decision-review trail, not a pesticide execution or spray permit.
-- Renumbered from the owner delivery's v266 (v257-v261 are taken elsewhere). Owner phase 11.
-- Tenant owner (credential issuer) = users.role 'owner' or 'admin' (see v270).
-- Explicit two-person review, no automatic routing to irrigation or sprayers.
BEGIN;
SET LOCAL lock_timeout='15s';
ALTER TABLE scout_photo_field_access_grants DROP CONSTRAINT IF EXISTS scout_photo_field_access_grants_scope_check;
ALTER TABLE scout_photo_field_access_grants ADD CONSTRAINT scout_photo_field_access_grants_scope_check
 CHECK (scope IN ('photo.read','photo.upload','photo.context','photo.season_link',
 'photo.detection_link','photo.lab_link','photo.diagnosis_review','photo.tissue_sample','photo.treatment_review'));
ALTER TABLE scout_photo_grant_audit_events DROP CONSTRAINT IF EXISTS scout_photo_grant_audit_events_scope_check;
ALTER TABLE scout_photo_grant_audit_events ADD CONSTRAINT scout_photo_grant_audit_events_scope_check
 CHECK (scope IN ('photo.read','photo.upload','photo.context','photo.season_link',
 'photo.detection_link','photo.lab_link','photo.diagnosis_review','photo.tissue_sample','photo.treatment_review'));
CREATE TABLE IF NOT EXISTS scout_treatment_review_events (
 event_id UUID PRIMARY KEY,
 tenant_id UUID NOT NULL,
 field_id TEXT NOT NULL,
 pin_id TEXT NOT NULL,
 action TEXT NOT NULL CHECK(action IN ('propose','review','reject','withdraw')),
 plan_sha256 CHAR(64),
 source_review_event_id UUID,
 previous_event_id UUID,
 actor_user_id INTEGER NOT NULL,
 reason TEXT NOT NULL CHECK(length(btrim(reason)) BETWEEN 20 AND 2000),
 recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CONSTRAINT scout_treatment_photo_fk FOREIGN KEY(tenant_id,field_id,pin_id)
 REFERENCES scout_photo_evidence(tenant_id,field_id,pin_id),
 CONSTRAINT scout_treatment_actor_fk FOREIGN KEY(tenant_id,actor_user_id)
 REFERENCES users(tenant_id,id),
 CONSTRAINT scout_treatment_human_review_fk FOREIGN KEY(source_review_event_id,tenant_id,field_id,pin_id)
 REFERENCES scout_photo_human_review_events(event_id,tenant_id,field_id,pin_id),
 CONSTRAINT scout_treatment_scope_uq UNIQUE(event_id,tenant_id,field_id,pin_id),
 CONSTRAINT scout_treatment_prev_fk FOREIGN KEY(previous_event_id,tenant_id,field_id,pin_id)
 REFERENCES scout_treatment_review_events(event_id,tenant_id,field_id,pin_id),
 CONSTRAINT scout_treatment_successor_uq UNIQUE(previous_event_id),
 CONSTRAINT scout_treatment_shape CHECK (
  (action='propose' AND previous_event_id IS NULL AND source_review_event_id IS NOT NULL AND plan_sha256 IS NOT NULL AND plan_sha256 ~ '^[a-f0-9]{64}$')
  OR (action<>'propose' AND previous_event_id IS NOT NULL AND source_review_event_id IS NULL AND plan_sha256 IS NULL)),
 CONSTRAINT scout_treatment_not_self CHECK(previous_event_id IS NULL OR previous_event_id<>event_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS scout_treatment_root_uq ON scout_treatment_review_events
(tenant_id,field_id,pin_id) WHERE previous_event_id IS NULL;
CREATE INDEX IF NOT EXISTS scout_treatment_history_idx ON scout_treatment_review_events
(tenant_id,field_id,pin_id,recorded_at DESC);
ALTER TABLE scout_treatment_review_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE scout_treatment_review_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS scout_treatment_tenant ON scout_treatment_review_events;
CREATE POLICY scout_treatment_tenant ON scout_treatment_review_events
 USING (tenant_id::text=NULLIF(current_setting('app.current_tenant',true),''))
 WITH CHECK (tenant_id::text=NULLIF(current_setting('app.current_tenant',true),''));
CREATE OR REPLACE FUNCTION scout_treatment_guard() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE previous_action TEXT; proposal_actor INTEGER; diagnosis_assessment TEXT;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'scout_treatment_immutable' USING ERRCODE='55000'; END IF;
 IF NOT EXISTS(SELECT 1 FROM users u JOIN scout_photo_field_access_grants g ON g.tenant_id=u.tenant_id
   AND g.user_id=u.id WHERE u.tenant_id=NEW.tenant_id AND u.id=NEW.actor_user_id
   AND u.active IS TRUE AND lower(u.role::text) IN ('expert','agronomist')
   AND g.field_id=NEW.field_id AND g.scope='photo.treatment_review'
   AND g.revoked_at IS NULL AND g.granted_at<=now() AND g.expires_at>now()
   AND g.expires_at<=g.granted_at+interval '90 days') THEN
    RAISE EXCEPTION 'scout_treatment_actor_unauthorized' USING ERRCODE='42501';
 END IF;
 -- Neither the proposer nor the second reviewer can rely on a role alone.
 IF NOT EXISTS (SELECT 1 FROM scout_specialist_credential_events c
   JOIN users issuer ON issuer.tenant_id=c.tenant_id AND issuer.id=c.actor_user_id
   WHERE c.tenant_id=NEW.tenant_id AND c.subject_user_id=NEW.actor_user_id
     AND c.discipline='crop_protection' AND c.action='attest_registry_check'
     AND c.expires_at>now() AND issuer.active IS TRUE AND lower(issuer.role::text) IN ('owner','admin')
     AND NOT EXISTS (SELECT 1 FROM scout_specialist_credential_events n WHERE n.previous_event_id=c.event_id)) THEN
     RAISE EXCEPTION 'scout_treatment_current_credential_required' USING ERRCODE='42501'; END IF;
 IF NEW.action='propose' THEN
    SELECT assessment INTO diagnosis_assessment FROM scout_photo_human_review_events r
      WHERE r.event_id=NEW.source_review_event_id AND r.tenant_id=NEW.tenant_id
      AND r.field_id=NEW.field_id AND r.pin_id=NEW.pin_id AND r.action='review'
      AND NOT EXISTS(SELECT 1 FROM scout_photo_human_review_events n WHERE n.previous_event_id=r.event_id);
    IF diagnosis_assessment IS NULL OR diagnosis_assessment IN ('ruled_out','inconclusive') THEN
      RAISE EXCEPTION 'scout_treatment_missing_review_basis' USING ERRCODE='23514'; END IF;
 ELSE
    SELECT action INTO previous_action FROM scout_treatment_review_events
     WHERE event_id=NEW.previous_event_id AND tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND pin_id=NEW.pin_id;
    IF previous_action IS NULL OR previous_action IN ('review','reject','withdraw') THEN
      RAISE EXCEPTION 'scout_treatment_invalid_transition' USING ERRCODE='23514'; END IF;
    IF NEW.action='review' AND EXISTS(
       SELECT 1 FROM scout_treatment_review_events p WHERE p.event_id=NEW.previous_event_id
          AND p.actor_user_id=NEW.actor_user_id) THEN
      RAISE EXCEPTION 'scout_treatment_two_person_rule' USING ERRCODE='42501'; END IF;
 END IF;
 RETURN NEW;
END; $$;
DROP TRIGGER IF EXISTS scout_treatment_review_guard ON scout_treatment_review_events;
CREATE TRIGGER scout_treatment_review_guard BEFORE INSERT OR UPDATE OR DELETE ON scout_treatment_review_events
 FOR EACH ROW EXECUTE FUNCTION scout_treatment_guard();
REVOKE ALL ON scout_treatment_review_events FROM PUBLIC;
COMMENT ON TABLE scout_treatment_review_events IS 'Two-person plan review only, execution_authorized is always false; product registration and jurisdiction not evaluated.';
COMMIT;
