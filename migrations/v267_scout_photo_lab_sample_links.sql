-- v267: Explicit photo -> soil/water sampling context. NOT a plant tissue diagnosis.
-- Renumbered from the owner delivery's v262 (v257-v261 are taken elsewhere). Owner phase 9.
-- The referenced sample is platform-owned and remains in the original lab workflow.
-- No auto-link based on coordinate, crop, timestamp, pin text or JSON origin.
BEGIN;
SET LOCAL lock_timeout = '15s';

ALTER TABLE scout_photo_field_access_grants
  DROP CONSTRAINT IF EXISTS scout_photo_field_access_grants_scope_check;
ALTER TABLE scout_photo_field_access_grants
  ADD CONSTRAINT scout_photo_field_access_grants_scope_check
  CHECK (scope IN ('photo.read','photo.upload','photo.context','photo.season_link',
                  'photo.detection_link','photo.lab_link'));
ALTER TABLE scout_photo_grant_audit_events
  DROP CONSTRAINT IF EXISTS scout_photo_grant_audit_events_scope_check;
ALTER TABLE scout_photo_grant_audit_events
  ADD CONSTRAINT scout_photo_grant_audit_events_scope_check
  CHECK (scope IN ('photo.read','photo.upload','photo.context','photo.season_link',
                  'photo.detection_link','photo.lab_link'));

-- Explicit FK from the composite immutable evidence identity to the lab sample
-- within the *same* tenant and field; global sample_id alone is insufficient.
CREATE UNIQUE INDEX IF NOT EXISTS scout_photo_lab_sample_scope_uq
  ON lab_samples (tenant_id,field_id,sample_id);
CREATE TABLE IF NOT EXISTS scout_photo_lab_link_events (
  event_id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  field_id TEXT NOT NULL,
  pin_id TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('link','revoke')),
  sample_id VARCHAR(64),
  previous_event_id UUID,
  actor_id TEXT NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 200),
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT scout_photo_lab_action_ck CHECK (
    (action='link' AND sample_id IS NOT NULL)
    OR (action='revoke' AND sample_id IS NULL AND previous_event_id IS NOT NULL AND reason IS NOT NULL
        AND length(btrim(reason)) BETWEEN 10 AND 2000)),
  CONSTRAINT scout_photo_lab_revision_ck CHECK (
    previous_event_id IS NULL OR (previous_event_id <> event_id
        AND reason IS NOT NULL AND length(btrim(reason)) BETWEEN 10 AND 2000)),
  CONSTRAINT scout_photo_lab_photo_fk FOREIGN KEY (tenant_id,field_id,pin_id)
    REFERENCES scout_photo_evidence(tenant_id,field_id,pin_id) ON DELETE RESTRICT,
  CONSTRAINT scout_photo_lab_sample_fk FOREIGN KEY (tenant_id,field_id,sample_id)
    REFERENCES lab_samples(tenant_id,field_id,sample_id) ON DELETE RESTRICT,
  CONSTRAINT scout_photo_lab_chain_scope_uq UNIQUE(event_id,tenant_id,field_id,pin_id),
  CONSTRAINT scout_photo_lab_prev_fk FOREIGN KEY(previous_event_id,tenant_id,field_id,pin_id)
    REFERENCES scout_photo_lab_link_events(event_id,tenant_id,field_id,pin_id),
  CONSTRAINT scout_photo_lab_successor_uq UNIQUE(previous_event_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS scout_photo_lab_root_uq
  ON scout_photo_lab_link_events(tenant_id,field_id,pin_id)
  WHERE previous_event_id IS NULL;
CREATE INDEX IF NOT EXISTS scout_photo_lab_history_idx
  ON scout_photo_lab_link_events(tenant_id,field_id,pin_id,created_at DESC);
ALTER TABLE scout_photo_lab_link_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE scout_photo_lab_link_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS scout_photo_lab_link_tenant ON scout_photo_lab_link_events;
CREATE POLICY scout_photo_lab_link_tenant ON scout_photo_lab_link_events
  USING (tenant_id::text=NULLIF(current_setting('app.current_tenant',true),''))
  WITH CHECK (tenant_id::text=NULLIF(current_setting('app.current_tenant',true),''));

CREATE OR REPLACE FUNCTION guard_scout_photo_lab_link_event() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'scout_photo_lab_link_immutable' USING ERRCODE='55000';
  END IF;
  IF NEW.action='link' AND NOT EXISTS (
    SELECT 1 FROM lab_samples s WHERE s.tenant_id=NEW.tenant_id
      AND s.field_id=NEW.field_id AND s.sample_id=NEW.sample_id
      AND s.kind IN ('soil','water') AND s.status IN ('sampled','in_lab','result_received','approved','published')
  ) THEN
    RAISE EXCEPTION 'scout_photo_lab_sample_invalid' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS scout_photo_lab_link_guard ON scout_photo_lab_link_events;
CREATE TRIGGER scout_photo_lab_link_guard
  BEFORE INSERT OR UPDATE OR DELETE ON scout_photo_lab_link_events
  FOR EACH ROW EXECUTE FUNCTION guard_scout_photo_lab_link_event();
REVOKE ALL ON scout_photo_lab_link_events FROM PUBLIC;
COMMENT ON TABLE scout_photo_lab_link_events IS
  'Explicit contextual link to platform soil/water sampling evidence; neither plant tissue analysis nor diagnosis.';
COMMIT;
