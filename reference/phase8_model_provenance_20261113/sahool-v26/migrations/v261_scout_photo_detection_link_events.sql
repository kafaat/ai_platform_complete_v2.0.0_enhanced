-- v261: Explicit, revisable photo -> ATTESTED model-output provenance link.
-- Source equality is proved from the persisted image SHA256, not filenames,
-- timestamps, proximity, GPS, crop, or a label guessed by the UI.
-- Model evidence remains UNREVIEWED. No plant diagnosis or pesticide authority.
BEGIN;
SET LOCAL lock_timeout = '15s';

-- A distinct privilege makes binding model output stricter than reading a photo.
ALTER TABLE scout_photo_field_access_grants
    DROP CONSTRAINT IF EXISTS scout_photo_field_access_grants_scope_check;
ALTER TABLE scout_photo_field_access_grants
    ADD CONSTRAINT scout_photo_field_access_grants_scope_check
    CHECK (scope IN ('photo.read','photo.upload','photo.context',
                    'photo.season_link','photo.detection_link'));
ALTER TABLE scout_photo_grant_audit_events
    DROP CONSTRAINT IF EXISTS scout_photo_grant_audit_events_scope_check;
ALTER TABLE scout_photo_grant_audit_events
    ADD CONSTRAINT scout_photo_grant_audit_events_scope_check
    CHECK (scope IN ('photo.read','photo.upload','photo.context',
                    'photo.season_link','photo.detection_link'));

-- Immutable component keys; no cross-tenant or cross-field output pointers.
CREATE UNIQUE INDEX IF NOT EXISTS scout_photo_detection_prov_tenant_result_uq
    ON detection_provenance(id,tenant_id,edge_result_id);
CREATE UNIQUE INDEX IF NOT EXISTS scout_photo_edge_result_field_uq
    ON edge_results(id,tenant_id,field_id);

CREATE TABLE IF NOT EXISTS scout_photo_detection_link_events (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    pin_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('link','revoke')),
    detection_provenance_id BIGINT,
    edge_result_id BIGINT,
    previous_event_id UUID,
    actor_id TEXT NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 200),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT scout_photo_detection_link_action_ck CHECK (
       (action='link' AND detection_provenance_id IS NOT NULL AND edge_result_id IS NOT NULL)
       OR (action='revoke' AND detection_provenance_id IS NULL AND edge_result_id IS NULL
           AND reason IS NOT NULL AND length(btrim(reason)) BETWEEN 1 AND 2000)
    ),
    CONSTRAINT scout_photo_detection_link_reason_ck CHECK (
       previous_event_id IS NULL OR (previous_event_id <> event_id AND reason IS NOT NULL
                                      AND length(btrim(reason)) BETWEEN 1 AND 2000)
    ),
    CONSTRAINT scout_photo_detection_link_photo_fk FOREIGN KEY (tenant_id,field_id,pin_id)
       REFERENCES scout_photo_evidence(tenant_id,field_id,pin_id) ON DELETE RESTRICT,
    CONSTRAINT scout_photo_detection_link_prov_fk
       FOREIGN KEY (detection_provenance_id,tenant_id,edge_result_id)
       REFERENCES detection_provenance(id,tenant_id,edge_result_id) ON DELETE RESTRICT,
    CONSTRAINT scout_photo_detection_link_edge_fk
       FOREIGN KEY (edge_result_id,tenant_id,field_id)
       REFERENCES edge_results(id,tenant_id,field_id) ON DELETE RESTRICT,
    CONSTRAINT scout_photo_detection_link_scope_uq UNIQUE(event_id,tenant_id,field_id,pin_id),
    CONSTRAINT scout_photo_detection_link_prev_fk
       FOREIGN KEY(previous_event_id,tenant_id,field_id,pin_id)
       REFERENCES scout_photo_detection_link_events(event_id,tenant_id,field_id,pin_id),
    CONSTRAINT scout_photo_detection_link_successor_uq UNIQUE(previous_event_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS scout_photo_detection_link_root_uq
    ON scout_photo_detection_link_events(tenant_id,field_id,pin_id)
    WHERE previous_event_id IS NULL;
CREATE INDEX IF NOT EXISTS scout_photo_detection_link_chain_idx
    ON scout_photo_detection_link_events(tenant_id,field_id,pin_id,created_at DESC);

ALTER TABLE scout_photo_detection_link_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE scout_photo_detection_link_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS scout_photo_detection_link_tenant ON scout_photo_detection_link_events;
CREATE POLICY scout_photo_detection_link_tenant ON scout_photo_detection_link_events
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant',true),''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant',true),''));

CREATE OR REPLACE FUNCTION guard_scout_photo_detection_link_event() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'scout_photo_detection_link_immutable' USING ERRCODE='55000';
  END IF;
  IF NEW.action='link' AND NOT EXISTS (
    SELECT 1 FROM scout_photo_evidence p
    JOIN detection_provenance d ON d.id=NEW.detection_provenance_id
        AND d.tenant_id=p.tenant_id AND d.edge_result_id=NEW.edge_result_id
    JOIN edge_results r ON r.id=d.edge_result_id AND r.tenant_id=d.tenant_id
    WHERE p.tenant_id=NEW.tenant_id AND p.field_id=NEW.field_id AND p.pin_id=NEW.pin_id
      AND r.field_id=NEW.field_id AND d.attestation='attested'
      AND d.input_sha256=p.content_sha256
  ) THEN
    RAISE EXCEPTION 'scout_photo_detection_image_provenance_mismatch'
      USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS scout_photo_detection_link_guard ON scout_photo_detection_link_events;
CREATE TRIGGER scout_photo_detection_link_guard
    BEFORE INSERT OR UPDATE OR DELETE ON scout_photo_detection_link_events
    FOR EACH ROW EXECUTE FUNCTION guard_scout_photo_detection_link_event();
REVOKE ALL ON scout_photo_detection_link_events FROM PUBLIC;
COMMENT ON TABLE scout_photo_detection_link_events IS
 'Human-explicit link to model output with exact image SHA256, field and tenant proof. NOT a diagnosis/actuation decision.';
COMMIT;
