-- v272: Append-only per-tenant retention policy and per-photo legal holds.
-- Renumbered from the owner delivery's v267 (v257-v261 are taken elsewhere). Owner phase 11.
-- Tenant owner = users.role 'owner' or 'admin' (see v270). Policies are dropped
-- before they are created, so a re-applied MANIFEST does not fail (the delivery's did), and the
-- guard branches per table (the delivery's guard failed every policy INSERT).
-- No physical deletion route. Immutable evidence and legal holds cannot be bypassed by worker
-- roles.
BEGIN;
SET LOCAL lock_timeout='15s';
CREATE TABLE IF NOT EXISTS scout_photo_retention_policy_events (
 event_id UUID PRIMARY KEY,
 tenant_id UUID NOT NULL,
 previous_event_id UUID,
 min_retention_days INTEGER NOT NULL CHECK(min_retention_days BETWEEN 365 AND 3650),
 actor_user_id INTEGER NOT NULL,
 reason TEXT NOT NULL CHECK(length(btrim(reason)) BETWEEN 20 AND 2000),
 recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CONSTRAINT scout_retention_policy_actor_fk FOREIGN KEY(tenant_id,actor_user_id) REFERENCES users(tenant_id,id),
 CONSTRAINT scout_retention_policy_scope_uq UNIQUE(event_id,tenant_id),
 CONSTRAINT scout_retention_policy_prev_fk FOREIGN KEY(previous_event_id,tenant_id)
 REFERENCES scout_photo_retention_policy_events(event_id,tenant_id),
 CONSTRAINT scout_retention_policy_successor_uq UNIQUE(previous_event_id),
 CONSTRAINT scout_retention_policy_not_self CHECK(previous_event_id IS NULL OR previous_event_id<>event_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS scout_retention_policy_root_uq
 ON scout_photo_retention_policy_events(tenant_id) WHERE previous_event_id IS NULL;
CREATE TABLE IF NOT EXISTS scout_photo_retention_events (
 event_id UUID PRIMARY KEY,
 tenant_id UUID NOT NULL,
 field_id TEXT NOT NULL,
 pin_id TEXT NOT NULL,
 action TEXT NOT NULL CHECK(action IN ('legal_hold','release_hold','request_disposition','deny_disposition')),
 previous_event_id UUID,
 actor_user_id INTEGER NOT NULL,
 reason TEXT NOT NULL CHECK(length(btrim(reason)) BETWEEN 20 AND 2000),
 recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CONSTRAINT scout_retention_photo_fk FOREIGN KEY(tenant_id,field_id,pin_id)
 REFERENCES scout_photo_evidence(tenant_id,field_id,pin_id),
 CONSTRAINT scout_retention_actor_fk FOREIGN KEY(tenant_id,actor_user_id) REFERENCES users(tenant_id,id),
 CONSTRAINT scout_retention_scope_uq UNIQUE(event_id,tenant_id,field_id,pin_id),
 CONSTRAINT scout_retention_prev_fk FOREIGN KEY(previous_event_id,tenant_id,field_id,pin_id)
 REFERENCES scout_photo_retention_events(event_id,tenant_id,field_id,pin_id),
 CONSTRAINT scout_retention_successor_uq UNIQUE(previous_event_id),
 CONSTRAINT scout_retention_not_self CHECK(previous_event_id IS NULL OR previous_event_id<>event_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS scout_retention_root_uq ON scout_photo_retention_events
 (tenant_id,field_id,pin_id) WHERE previous_event_id IS NULL;
CREATE INDEX IF NOT EXISTS scout_retention_history_idx ON scout_photo_retention_events
 (tenant_id,field_id,pin_id,recorded_at DESC);
DO $$ DECLARE tbl TEXT; BEGIN
 FOREACH tbl IN ARRAY ARRAY['scout_photo_retention_policy_events','scout_photo_retention_events'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',tbl);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',tbl);
  EXECUTE format('DROP POLICY IF EXISTS %I ON %I',tbl||'_tenant',tbl);
  EXECUTE format('CREATE POLICY %I ON %I USING (tenant_id::text=NULLIF(current_setting(''app.current_tenant'',true),'''')) WITH CHECK (tenant_id::text=NULLIF(current_setting(''app.current_tenant'',true),''''))',tbl||'_tenant',tbl);
 END LOOP;
END $$;
CREATE OR REPLACE FUNCTION scout_retention_guard() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE prev_action TEXT; prev_days INTEGER;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'scout_retention_history_immutable' USING ERRCODE='55000'; END IF;
 IF NOT EXISTS (SELECT 1 FROM users u WHERE u.tenant_id=NEW.tenant_id AND u.id=NEW.actor_user_id
   AND u.active IS TRUE AND lower(u.role::text) IN ('owner','admin')) THEN
   RAISE EXCEPTION 'scout_retention_owner_required' USING ERRCODE='42501'; END IF;
 -- One branch per table: PL/pgSQL resolves NEW.<column> when the expression is evaluated, so a
 -- condition naming NEW.action on a policy row fails even behind "TG_TABLE_NAME=... AND" (the
 -- delivery's single-expression form made every policy INSERT fail with 42703).
 IF TG_TABLE_NAME='scout_photo_retention_policy_events' THEN
   IF NEW.previous_event_id IS NOT NULL THEN
     SELECT min_retention_days INTO prev_days FROM scout_photo_retention_policy_events
     WHERE event_id=NEW.previous_event_id AND tenant_id=NEW.tenant_id;
     IF prev_days IS NULL OR NEW.min_retention_days < prev_days THEN
        RAISE EXCEPTION 'scout_retention_minimum_cannot_decrease' USING ERRCODE='23514';
     END IF;
   END IF;
   RETURN NEW;
 END IF;
 -- Asking to dispose is not approval, but must not precede the minimum lease.
 IF NEW.action='request_disposition' THEN
   IF NOT EXISTS (SELECT 1 FROM scout_photo_evidence photo
     JOIN scout_photo_retention_policy_events p ON p.tenant_id=photo.tenant_id
     WHERE photo.tenant_id=NEW.tenant_id AND photo.field_id=NEW.field_id
       AND photo.pin_id=NEW.pin_id
       AND NOT EXISTS (SELECT 1 FROM scout_photo_retention_policy_events n
           WHERE n.previous_event_id=p.event_id)
       AND now() >= photo.uploaded_at + make_interval(days => p.min_retention_days)) THEN
      RAISE EXCEPTION 'scout_retention_minimum_not_satisfied' USING ERRCODE='23514';
   END IF;
 END IF;
 IF NEW.previous_event_id IS NOT NULL THEN
   SELECT action INTO prev_action FROM scout_photo_retention_events
   WHERE event_id=NEW.previous_event_id AND tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND pin_id=NEW.pin_id;
   IF prev_action IS NULL OR (prev_action='legal_hold' AND NEW.action<>'release_hold')
     OR (NEW.action='release_hold' AND prev_action<>'legal_hold')
     OR (NEW.action='deny_disposition' AND prev_action<>'request_disposition')
     OR (prev_action='request_disposition' AND NEW.action NOT IN ('deny_disposition','legal_hold')) THEN
     RAISE EXCEPTION 'scout_retention_invalid_transition' USING ERRCODE='23514'; END IF;
 ELSIF NEW.action IN ('release_hold','deny_disposition') THEN
   RAISE EXCEPTION 'scout_retention_prior_event_required' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$;
DROP TRIGGER IF EXISTS scout_retention_policy_guard ON scout_photo_retention_policy_events;
CREATE TRIGGER scout_retention_policy_guard BEFORE INSERT OR UPDATE OR DELETE ON scout_photo_retention_policy_events
 FOR EACH ROW EXECUTE FUNCTION scout_retention_guard();
DROP TRIGGER IF EXISTS scout_retention_event_guard ON scout_photo_retention_events;
CREATE TRIGGER scout_retention_event_guard BEFORE INSERT OR UPDATE OR DELETE ON scout_photo_retention_events
 FOR EACH ROW EXECUTE FUNCTION scout_retention_guard();
REVOKE ALL ON scout_photo_retention_policy_events,scout_photo_retention_events FROM PUBLIC;
COMMENT ON TABLE scout_photo_retention_events IS 'Legal hold and disposition review events, no physical purge permission or background deletion.';
COMMIT;
