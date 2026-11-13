-- v268: Expert-authored review of a persisted photo, never chemical actuation.
-- Renumbered from the owner delivery's v263 (v257-v261 are taken elsewhere). Owner phase 9.
-- A role+field grant is not proof of professional licensing; review provenance
-- is recorded as an explicit human assertion, not externally certified diagnosis.
BEGIN;
SET LOCAL lock_timeout = '15s';
ALTER TABLE scout_photo_field_access_grants
  DROP CONSTRAINT IF EXISTS scout_photo_field_access_grants_scope_check;
ALTER TABLE scout_photo_field_access_grants
  ADD CONSTRAINT scout_photo_field_access_grants_scope_check
  CHECK (scope IN ('photo.read','photo.upload','photo.context','photo.season_link',
                  'photo.detection_link','photo.lab_link','photo.diagnosis_review'));
ALTER TABLE scout_photo_grant_audit_events
  DROP CONSTRAINT IF EXISTS scout_photo_grant_audit_events_scope_check;
ALTER TABLE scout_photo_grant_audit_events
  ADD CONSTRAINT scout_photo_grant_audit_events_scope_check
  CHECK (scope IN ('photo.read','photo.upload','photo.context','photo.season_link',
                  'photo.detection_link','photo.lab_link','photo.diagnosis_review'));

CREATE TABLE IF NOT EXISTS scout_photo_human_review_events (
  event_id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  field_id TEXT NOT NULL,
  pin_id TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('review','retract')),
  assessment TEXT CHECK (assessment IN ('suspected','ruled_out','requires_lab','inconclusive')),
  diagnosis_code TEXT,
  review_method TEXT CHECK (review_method IN ('photo_review','field_exam')),
  image_sha256 CHAR(64),
  previous_event_id UUID,
  reviewer_user_id INTEGER NOT NULL,
  reason TEXT NOT NULL CHECK (length(btrim(reason)) BETWEEN 20 AND 2000),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT scout_photo_human_action_ck CHECK (
    (action='review' AND assessment IS NOT NULL AND review_method IS NOT NULL
      AND image_sha256 ~ '^[a-f0-9]{64}$'
      AND ((assessment='suspected' AND diagnosis_code IS NOT NULL
          AND diagnosis_code ~ '^[a-z][a-z0-9_.-]{1,99}$')
        OR (assessment <> 'suspected' AND diagnosis_code IS NULL)))
    OR (action='retract' AND previous_event_id IS NOT NULL AND assessment IS NULL AND diagnosis_code IS NULL
      AND review_method IS NULL AND image_sha256 IS NULL)),
  CONSTRAINT scout_photo_human_revision_ck CHECK (
    previous_event_id IS NULL OR previous_event_id <> event_id),
  CONSTRAINT scout_photo_human_photo_fk FOREIGN KEY (tenant_id,field_id,pin_id)
    REFERENCES scout_photo_evidence(tenant_id,field_id,pin_id) ON DELETE RESTRICT,
  CONSTRAINT scout_photo_human_actor_fk FOREIGN KEY (tenant_id,reviewer_user_id)
    REFERENCES users(tenant_id,id) ON DELETE RESTRICT,
  CONSTRAINT scout_photo_human_chain_scope_uq UNIQUE(event_id,tenant_id,field_id,pin_id),
  CONSTRAINT scout_photo_human_prev_fk FOREIGN KEY(previous_event_id,tenant_id,field_id,pin_id)
    REFERENCES scout_photo_human_review_events(event_id,tenant_id,field_id,pin_id),
  CONSTRAINT scout_photo_human_successor_uq UNIQUE(previous_event_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS scout_photo_human_root_uq
  ON scout_photo_human_review_events(tenant_id,field_id,pin_id)
  WHERE previous_event_id IS NULL;
CREATE INDEX IF NOT EXISTS scout_photo_human_history_idx
  ON scout_photo_human_review_events(tenant_id,field_id,pin_id,created_at DESC);
ALTER TABLE scout_photo_human_review_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE scout_photo_human_review_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS scout_photo_human_review_tenant ON scout_photo_human_review_events;
CREATE POLICY scout_photo_human_review_tenant ON scout_photo_human_review_events
  USING (tenant_id::text=NULLIF(current_setting('app.current_tenant',true),''))
  WITH CHECK (tenant_id::text=NULLIF(current_setting('app.current_tenant',true),''));

CREATE OR REPLACE FUNCTION guard_scout_photo_human_review_event() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'scout_photo_human_review_immutable' USING ERRCODE='55000';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM users u
    WHERE u.tenant_id=NEW.tenant_id AND u.id=NEW.reviewer_user_id
      AND u.active IS TRUE AND lower(u.role::text) IN ('expert','agronomist')
  ) OR NOT EXISTS (
    SELECT 1 FROM scout_photo_field_access_grants g
    WHERE g.tenant_id=NEW.tenant_id AND g.field_id=NEW.field_id
      AND g.user_id=NEW.reviewer_user_id AND g.scope='photo.diagnosis_review'
      AND g.revoked_at IS NULL AND g.expires_at > now()
      AND g.expires_at <= g.granted_at + interval '90 days'
  ) THEN
    RAISE EXCEPTION 'scout_photo_reviewer_not_authorized' USING ERRCODE='42501';
  END IF;
  IF NEW.action='review' AND NOT EXISTS (
    SELECT 1 FROM scout_photo_evidence p WHERE p.tenant_id=NEW.tenant_id
      AND p.field_id=NEW.field_id AND p.pin_id=NEW.pin_id
      AND p.content_sha256=NEW.image_sha256
  ) THEN
    RAISE EXCEPTION 'scout_photo_human_image_hash_mismatch' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS scout_photo_human_review_guard ON scout_photo_human_review_events;
CREATE TRIGGER scout_photo_human_review_guard
  BEFORE INSERT OR UPDATE OR DELETE ON scout_photo_human_review_events
  FOR EACH ROW EXECUTE FUNCTION guard_scout_photo_human_review_event();
REVOKE ALL ON scout_photo_human_review_events FROM PUBLIC;
COMMENT ON TABLE scout_photo_human_review_events IS
  'Append-only human expert assessment; suspected/inconclusive only, no approved diagnosis or pesticide authorization.';
COMMIT;
