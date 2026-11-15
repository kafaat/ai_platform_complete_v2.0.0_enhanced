-- v269: Independent plant-tissue sampling with append-only chain of custody.
-- Renumbered from the owner delivery's v264 (v257-v261 are taken elsewhere). Owner phase 11.
-- NEVER reuse soil/water lab_samples or imply laboratory confirmation.
BEGIN;
SET LOCAL lock_timeout = '15s';
ALTER TABLE scout_photo_field_access_grants DROP CONSTRAINT IF EXISTS scout_photo_field_access_grants_scope_check;
ALTER TABLE scout_photo_field_access_grants ADD CONSTRAINT scout_photo_field_access_grants_scope_check
  CHECK (scope IN ('photo.read','photo.upload','photo.context','photo.season_link',
    'photo.detection_link','photo.lab_link','photo.diagnosis_review','photo.tissue_sample'));
ALTER TABLE scout_photo_grant_audit_events DROP CONSTRAINT IF EXISTS scout_photo_grant_audit_events_scope_check;
ALTER TABLE scout_photo_grant_audit_events ADD CONSTRAINT scout_photo_grant_audit_events_scope_check
  CHECK (scope IN ('photo.read','photo.upload','photo.context','photo.season_link',
    'photo.detection_link','photo.lab_link','photo.diagnosis_review','photo.tissue_sample'));

CREATE TABLE IF NOT EXISTS scout_plant_tissue_samples (
  sample_id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  field_id TEXT NOT NULL,
  pin_id TEXT NOT NULL,
  barcode TEXT NOT NULL CHECK (barcode ~ '^[A-Z0-9][A-Z0-9_-]{5,63}$'),
  specimen_type TEXT NOT NULL CHECK (specimen_type IN ('leaf','stem','root','fruit','flower','seed')),
  collected_at TIMESTAMPTZ NOT NULL,
  collected_by INTEGER NOT NULL,
  symptoms_note TEXT CHECK (symptoms_note IS NULL OR length(symptoms_note) <= 2000),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT scout_tissue_photo_fk FOREIGN KEY (tenant_id,field_id,pin_id)
    REFERENCES scout_photo_evidence(tenant_id,field_id,pin_id) ON DELETE RESTRICT,
  CONSTRAINT scout_tissue_collector_fk FOREIGN KEY (tenant_id,collected_by)
    REFERENCES users(tenant_id,id) ON DELETE RESTRICT,
  CONSTRAINT scout_tissue_scope_uq UNIQUE(sample_id,tenant_id,field_id,pin_id),
  CONSTRAINT scout_tissue_barcode_uq UNIQUE(tenant_id,barcode)
);
CREATE INDEX IF NOT EXISTS scout_tissue_photo_idx ON scout_plant_tissue_samples(tenant_id,field_id,pin_id);

CREATE TABLE IF NOT EXISTS scout_tissue_custody_events (
  event_id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  field_id TEXT NOT NULL,
  pin_id TEXT NOT NULL,
  sample_id UUID NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('collected','handed_over','received','rejected','disposed')),
  previous_event_id UUID,
  actor_user_id INTEGER NOT NULL,
  recipient_ref TEXT CHECK (recipient_ref IS NULL OR length(btrim(recipient_ref)) BETWEEN 3 AND 120),
  note TEXT NOT NULL CHECK (length(btrim(note)) BETWEEN 10 AND 2000),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT scout_tissue_custody_sample_fk FOREIGN KEY(sample_id,tenant_id,field_id,pin_id)
    REFERENCES scout_plant_tissue_samples(sample_id,tenant_id,field_id,pin_id) ON DELETE RESTRICT,
  CONSTRAINT scout_tissue_custody_actor_fk FOREIGN KEY(tenant_id,actor_user_id)
    REFERENCES users(tenant_id,id) ON DELETE RESTRICT,
  CONSTRAINT scout_tissue_custody_scope_uq UNIQUE(event_id,tenant_id,sample_id),
  CONSTRAINT scout_tissue_custody_previous_fk FOREIGN KEY(previous_event_id,tenant_id,sample_id)
    REFERENCES scout_tissue_custody_events(event_id,tenant_id,sample_id),
  CONSTRAINT scout_tissue_custody_successor_uq UNIQUE(previous_event_id),
  CONSTRAINT scout_tissue_custody_shape CHECK (
    (action='collected' AND previous_event_id IS NULL) OR
    (action<>'collected' AND previous_event_id IS NOT NULL AND previous_event_id<>event_id)),
  CONSTRAINT scout_tissue_custody_transfer CHECK (
    (action IN ('handed_over','received') AND recipient_ref IS NOT NULL) OR
    (action NOT IN ('handed_over','received') AND recipient_ref IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS scout_tissue_custody_root_uq
  ON scout_tissue_custody_events(tenant_id,sample_id) WHERE previous_event_id IS NULL;
CREATE INDEX IF NOT EXISTS scout_tissue_custody_history_idx
  ON scout_tissue_custody_events(tenant_id,sample_id,recorded_at,event_id);

ALTER TABLE scout_plant_tissue_samples ENABLE ROW LEVEL SECURITY;
ALTER TABLE scout_plant_tissue_samples FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS scout_tissue_sample_tenant ON scout_plant_tissue_samples;
CREATE POLICY scout_tissue_sample_tenant ON scout_plant_tissue_samples
  USING (tenant_id::text=NULLIF(current_setting('app.current_tenant',true),''))
  WITH CHECK (tenant_id::text=NULLIF(current_setting('app.current_tenant',true),''));
ALTER TABLE scout_tissue_custody_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE scout_tissue_custody_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS scout_tissue_custody_tenant ON scout_tissue_custody_events;
CREATE POLICY scout_tissue_custody_tenant ON scout_tissue_custody_events
  USING (tenant_id::text=NULLIF(current_setting('app.current_tenant',true),''))
  WITH CHECK (tenant_id::text=NULLIF(current_setting('app.current_tenant',true),''));

CREATE OR REPLACE FUNCTION scout_tissue_guard() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE prev_action TEXT;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'scout_tissue_immutable' USING ERRCODE='55000';
  END IF;
  IF TG_TABLE_NAME='scout_plant_tissue_samples' THEN
    IF NEW.collected_at > now() + interval '1 hour' OR NEW.collected_at < now()-interval '1 year' THEN
      RAISE EXCEPTION 'scout_tissue_collection_time_invalid' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM users u JOIN scout_photo_field_access_grants g
      ON g.tenant_id=u.tenant_id AND g.user_id=u.id
      WHERE u.tenant_id=NEW.tenant_id AND u.id=NEW.actor_user_id AND u.active IS TRUE
        AND lower(u.role::text) IN ('worker','manager','expert','agronomist')
        AND g.field_id=NEW.field_id AND g.scope='photo.tissue_sample'
        AND g.revoked_at IS NULL AND g.expires_at>now() AND g.granted_at<=now()
        AND g.expires_at<=g.granted_at+interval '90 days') THEN
    RAISE EXCEPTION 'scout_tissue_actor_not_authorized' USING ERRCODE='42501';
  END IF;
  IF NEW.action='collected' AND NOT EXISTS (
    SELECT 1 FROM scout_plant_tissue_samples s WHERE s.sample_id=NEW.sample_id
      AND s.tenant_id=NEW.tenant_id AND s.field_id=NEW.field_id
      AND s.pin_id=NEW.pin_id AND s.collected_by=NEW.actor_user_id) THEN
    RAISE EXCEPTION 'scout_tissue_collector_mismatch' USING ERRCODE='42501';
  END IF;
  IF NEW.action <> 'collected' THEN
    SELECT action INTO prev_action FROM scout_tissue_custody_events
      WHERE event_id=NEW.previous_event_id AND tenant_id=NEW.tenant_id AND sample_id=NEW.sample_id;
    IF prev_action IS NULL OR prev_action IN ('rejected','disposed')
      OR (NEW.action='received' AND prev_action<>'handed_over')
      OR (NEW.action='handed_over' AND prev_action NOT IN ('collected','received')) THEN
      RAISE EXCEPTION 'scout_tissue_illegal_custody_transition' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END; $$;
DROP TRIGGER IF EXISTS scout_tissue_sample_guard ON scout_plant_tissue_samples;
CREATE TRIGGER scout_tissue_sample_guard BEFORE INSERT OR UPDATE OR DELETE ON scout_plant_tissue_samples
  FOR EACH ROW EXECUTE FUNCTION scout_tissue_guard();
DROP TRIGGER IF EXISTS scout_tissue_custody_guard ON scout_tissue_custody_events;
CREATE TRIGGER scout_tissue_custody_guard BEFORE INSERT OR UPDATE OR DELETE ON scout_tissue_custody_events
  FOR EACH ROW EXECUTE FUNCTION scout_tissue_guard();
-- Deferred constraint requires the collection event in the same commit as
-- the sample. A direct SQL INSERT must not produce orphan tissue samples.
CREATE OR REPLACE FUNCTION scout_tissue_require_collection() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM scout_tissue_custody_events c
    WHERE c.tenant_id=NEW.tenant_id AND c.field_id=NEW.field_id
      AND c.pin_id=NEW.pin_id AND c.sample_id=NEW.sample_id
      AND c.action='collected' AND c.previous_event_id IS NULL
      AND c.actor_user_id=NEW.collected_by) THEN
    RAISE EXCEPTION 'scout_tissue_collection_event_missing' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END; $$;
DROP TRIGGER IF EXISTS scout_tissue_deferred_collection_guard ON scout_plant_tissue_samples;
CREATE CONSTRAINT TRIGGER scout_tissue_deferred_collection_guard
  AFTER INSERT ON scout_plant_tissue_samples DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION scout_tissue_require_collection();
REVOKE ALL ON scout_plant_tissue_samples,scout_tissue_custody_events FROM PUBLIC;
COMMENT ON TABLE scout_plant_tissue_samples IS 'Plant tissue sampling and photo provenance, no pathology result or release authority.';
COMMENT ON TABLE scout_tissue_custody_events IS 'Immutable, sequential custody; laboratory receipt is not test confirmation.';
COMMIT;
