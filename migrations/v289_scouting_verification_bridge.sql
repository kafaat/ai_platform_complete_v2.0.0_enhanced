-- v289 candidate: owner-local anomaly task -> pin inspection -> explicit reviewed assessment.
-- field-management-service owns all four tables. No change to v274/v277/v282:
-- anomaly tasks still have no pin; pin tasks retain their immutable pin and own evidence.
-- Numbers are checked again at integration; applying this locally enables no runtime flag.
BEGIN;
SET LOCAL lock_timeout = '15s';

CREATE TABLE IF NOT EXISTS scouting_verification_links (
    link_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    field_id varchar(50) NOT NULL,
    anomaly_task_id uuid NOT NULL,
    inspection_task_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    UNIQUE (tenant_id, field_id, link_id),
    UNIQUE (tenant_id, anomaly_task_id),
    UNIQUE (tenant_id, inspection_task_id),
    FOREIGN KEY (tenant_id, field_id, anomaly_task_id)
        REFERENCES field_tasks (tenant_id, field_id, task_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, field_id, inspection_task_id)
        REFERENCES field_tasks (tenant_id, field_id, task_id) ON DELETE RESTRICT,
    CHECK (anomaly_task_id <> inspection_task_id)
);

CREATE TABLE IF NOT EXISTS scouting_verification_versions (
    tenant_id uuid NOT NULL,
    field_id varchar(50) NOT NULL,
    link_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    command_id uuid NOT NULL,
    command_digest char(64) NOT NULL CHECK (command_digest::text ~ '^[0-9a-f]{64}$'),
    scope_snapshot jsonb NOT NULL CHECK (jsonb_typeof(scope_snapshot) = 'object'),
    context_digest char(64) NOT NULL CHECK (context_digest::text ~ '^[0-9a-f]{64}$'),
    anomaly_snapshot jsonb NOT NULL CHECK (jsonb_typeof(anomaly_snapshot) = 'object'),
    anomaly_snapshot_digest char(64) NOT NULL CHECK (anomaly_snapshot_digest::text ~ '^[0-9a-f]{64}$'),
    expected_anomaly_version integer NOT NULL CHECK (expected_anomaly_version > 0),
    created_by text NOT NULL CHECK (btrim(created_by) <> ''),
    created_role text NOT NULL,
    reason text NOT NULL CHECK (length(btrim(reason)) BETWEEN 1 AND 2000),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (link_id, revision),
    UNIQUE (tenant_id, command_id),
    UNIQUE (tenant_id, field_id, link_id, revision),
    FOREIGN KEY (tenant_id, field_id, link_id)
        REFERENCES scouting_verification_links (tenant_id, field_id, link_id) ON DELETE RESTRICT
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='scouting_verification_links'::regclass
                   AND conname='scout_verification_current_version_fk') THEN
        ALTER TABLE scouting_verification_links ADD CONSTRAINT scout_verification_current_version_fk
            FOREIGN KEY (link_id, revision) REFERENCES scouting_verification_versions (link_id, revision)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS scouting_verification_assessments (
    assessment_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    field_id varchar(50) NOT NULL,
    link_id uuid NOT NULL,
    link_revision integer NOT NULL,
    command_id uuid NOT NULL,
    command_digest char(64) NOT NULL CHECK (command_digest::text ~ '^[0-9a-f]{64}$'),
    inspection_revision integer NOT NULL CHECK (inspection_revision > 0),
    evidence_version integer NOT NULL CHECK (evidence_version > 0),
    reviewer text NOT NULL CHECK (btrim(reviewer) <> ''),
    reviewer_role text NOT NULL,
    assessment_text text NOT NULL CHECK (jsonb_typeof(assessment_text::jsonb) = 'object'),
    assessment_digest char(64) NOT NULL CHECK (
        assessment_digest = encode(sha256(convert_to(assessment_text, 'UTF8')), 'hex')),
    completed_at timestamptz NOT NULL,
    UNIQUE (tenant_id, field_id, assessment_id),
    UNIQUE (tenant_id, command_id),
    UNIQUE (link_id, link_revision),
    FOREIGN KEY (tenant_id, field_id, link_id, link_revision)
        REFERENCES scouting_verification_versions (tenant_id, field_id, link_id, revision)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS scouting_verification_outbox (
    delivery_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    field_id varchar(50) NOT NULL,
    assessment_id uuid NOT NULL UNIQUE,
    idempotency_key text NOT NULL,
    body_text text NOT NULL CHECK (jsonb_typeof(body_text::jsonb) = 'object'),
    body_digest char(64) NOT NULL CHECK (
        body_digest = encode(sha256(convert_to(body_text, 'UTF8')), 'hex')),
    state text NOT NULL DEFAULT 'pending' CHECK (state IN (
        'pending', 'sending', 'delivery_unknown', 'blocked', 'delivered', 'delivered_review_required',
        'delivery_exhausted')),
    lease_token uuid,
    lease_until timestamptz,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error text,
    receipt jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, field_id, assessment_id)
        REFERENCES scouting_verification_assessments (tenant_id, field_id, assessment_id)
        ON DELETE RESTRICT,
    CHECK ((lease_token IS NULL) = (lease_until IS NULL)),
    -- A lease exists exactly while a worker holds the row.
    CHECK ((state = 'sending') = (lease_token IS NOT NULL)),
    -- "Delivered" is a claim about the remote owner: it needs the receipt that proves it.
    CHECK (state NOT IN ('delivered', 'delivered_review_required') OR receipt IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_scout_verification_delivery_state
    ON scouting_verification_outbox (tenant_id, state, lease_until);

CREATE OR REPLACE FUNCTION scouting_verification_link_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE a record; b record;
BEGIN
    SELECT anomaly_ref, source_scouting_pin_id INTO a FROM public.field_tasks
        WHERE tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND task_id=NEW.anomaly_task_id;
    SELECT anomaly_ref, source_scouting_pin_id INTO b FROM public.field_tasks
        WHERE tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND task_id=NEW.inspection_task_id;
    IF a.anomaly_ref IS NULL OR a.source_scouting_pin_id IS NOT NULL
       OR b.source_scouting_pin_id IS NULL OR b.anomaly_ref IS NOT NULL THEN
        RAISE EXCEPTION 'verification_link_requires_separate_anomaly_and_pin_tasks' USING ERRCODE='23514';
    END IF;
    IF TG_OP='UPDATE' AND (NEW.link_id <> OLD.link_id OR NEW.tenant_id <> OLD.tenant_id
       OR NEW.field_id <> OLD.field_id OR NEW.anomaly_task_id <> OLD.anomaly_task_id
       OR NEW.revision <> OLD.revision + 1) THEN
        RAISE EXCEPTION 'verification_link_identity_or_revision_invalid' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS scouting_verification_link_guard ON scouting_verification_links;
CREATE TRIGGER scouting_verification_link_guard BEFORE INSERT OR UPDATE ON scouting_verification_links
    FOR EACH ROW EXECUTE FUNCTION scouting_verification_link_guard();

CREATE OR REPLACE FUNCTION scouting_verification_assessment_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE b uuid; h record; v record; p record;
BEGIN
    SELECT inspection_task_id INTO b FROM public.scouting_verification_links
        WHERE tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND link_id=NEW.link_id
          AND revision=NEW.link_revision;
    SELECT * INTO h FROM public.inspection_handoffs
        WHERE tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND task_id=b
        ORDER BY revision DESC LIMIT 1;
    SELECT * INTO v FROM public.inspection_evidence_versions
        WHERE tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND task_id=b
          AND version=NEW.evidence_version;
    SELECT e.evidence_id, e.content_sha256 INTO p FROM public.field_tasks t
        LEFT JOIN public.scout_photo_evidence e ON e.tenant_id=t.tenant_id
          AND e.field_id=t.field_id AND e.pin_id=t.source_scouting_pin_id
        WHERE t.tenant_id=NEW.tenant_id AND t.field_id=NEW.field_id AND t.task_id=b;
    IF b IS NULL OR h.action IS DISTINCT FROM 'approve' OR h.actor IS DISTINCT FROM NEW.reviewer
       OR h.revision IS DISTINCT FROM NEW.inspection_revision
       OR h.evidence_version IS DISTINCT FROM NEW.evidence_version
       OR h.assignee IS NOT DISTINCT FROM NEW.reviewer
       OR v.version IS NULL OR v.photo_evidence_id IS DISTINCT FROM p.evidence_id
       OR v.photo_content_sha256 IS DISTINCT FROM p.content_sha256 THEN
        RAISE EXCEPTION 'verification_assessment_requires_current_reviewed_evidence' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS scouting_verification_assessment_guard ON scouting_verification_assessments;
CREATE TRIGGER scouting_verification_assessment_guard BEFORE INSERT ON scouting_verification_assessments
    FOR EACH ROW EXECUTE FUNCTION scouting_verification_assessment_guard();

CREATE OR REPLACE FUNCTION scouting_verification_delivery_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF NEW.delivery_id <> OLD.delivery_id OR NEW.tenant_id <> OLD.tenant_id
       OR NEW.field_id <> OLD.field_id OR NEW.assessment_id <> OLD.assessment_id
       OR NEW.idempotency_key <> OLD.idempotency_key OR NEW.body_text <> OLD.body_text
       OR NEW.body_digest <> OLD.body_digest OR NEW.created_at <> OLD.created_at THEN
        RAISE EXCEPTION 'verification_delivery_content_immutable' USING ERRCODE='55000';
    END IF;
    -- The delivery state machine, enforced here and not only in field-management's Python:
    --   pending          -> sending | blocked (link superseded before any send)
    --   delivery_unknown -> sending
    --   sending          -> sending (reclaim only after the lease expired)
    --                     | delivered | delivered_review_required | blocked | delivery_unknown
    --   pending | delivery_unknown | sending (lease expired) -> delivery_exhausted
    --                                                          (only at the attempt cap, 8)
    -- delivered, delivered_review_required, blocked and delivery_exhausted are terminal.
    IF NOT (
        (OLD.state = 'pending' AND NEW.state IN ('sending', 'blocked'))
        OR (OLD.state = 'delivery_unknown' AND NEW.state = 'sending')
        OR (OLD.state = 'sending' AND NEW.state = 'sending' AND OLD.lease_until <= clock_timestamp())
        OR (OLD.state = 'sending' AND NEW.state IN (
            'delivered', 'delivered_review_required', 'blocked', 'delivery_unknown'))
        OR (OLD.state IN ('pending', 'delivery_unknown') AND NEW.state = 'delivery_exhausted'
            AND OLD.attempts >= 8)
        OR (OLD.state = 'sending' AND NEW.state = 'delivery_exhausted' AND OLD.attempts >= 8
            AND OLD.lease_until <= clock_timestamp())
    ) THEN
        RAISE EXCEPTION 'verification_delivery_transition_refused: % -> %', OLD.state, NEW.state
            USING ERRCODE='55000';
    END IF;
    IF NEW.state = 'sending' AND NEW.attempts > 8 THEN
        RAISE EXCEPTION 'verification_delivery_attempts_exhausted' USING ERRCODE='55000';
    END IF;
    -- Each claim counts one attempt; nothing else changes the count.
    IF (NEW.state = 'sending' AND NEW.attempts <> OLD.attempts + 1)
       OR (NEW.state <> 'sending' AND NEW.attempts <> OLD.attempts) THEN
        RAISE EXCEPTION 'verification_delivery_attempts_tampered' USING ERRCODE='55000';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS scouting_verification_delivery_guard ON scouting_verification_outbox;
CREATE TRIGGER scouting_verification_delivery_guard BEFORE UPDATE ON scouting_verification_outbox
    FOR EACH ROW EXECUTE FUNCTION scouting_verification_delivery_guard();
DROP TRIGGER IF EXISTS scouting_verification_delivery_delete_guard ON scouting_verification_outbox;
CREATE TRIGGER scouting_verification_delivery_delete_guard BEFORE DELETE ON scouting_verification_outbox
    FOR EACH ROW EXECUTE FUNCTION field_mgmt_append_only();

CREATE OR REPLACE FUNCTION scouting_verification_delivery_insert_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE a record; v record; b jsonb; e jsonb; r jsonb; expected_ref text;
BEGIN
    SELECT * INTO a FROM public.scouting_verification_assessments
        WHERE tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND assessment_id=NEW.assessment_id;
    SELECT * INTO v FROM public.scouting_verification_versions WHERE link_id=a.link_id AND revision=a.link_revision;
    b := NEW.body_text::jsonb;
    r := a.assessment_text::jsonb;
    expected_ref := 'urn:sahool:evidence:scout-' || replace(a.assessment_id::text,'-','');
    IF a.assessment_id IS NULL OR v.link_id IS NULL
       OR b->>'task_ref' IS DISTINCT FROM 'urn:sahool:task:' || (v.scope_snapshot->>'anomaly_task_id')
       OR b->>'expected_version' IS DISTINCT FROM v.expected_anomaly_version::text
       OR b->>'verification_result' IS DISTINCT FROM r->'request'->>'verification_result'
       OR b->>'completed_at' IS DISTINCT FROM r->>'completed_at'
       OR b->'reason_codes' IS DISTINCT FROM r->'request'->'reason_codes'
       OR b->'evidence_refs' IS DISTINCT FROM jsonb_build_array(expected_ref)
       OR jsonb_typeof(b->'evidence') IS DISTINCT FROM 'array'
       OR jsonb_array_length(b->'evidence') <> 1 THEN
        RAISE EXCEPTION 'verification_delivery_does_not_match_reviewed_assessment' USING ERRCODE='23514';
    END IF;
    e := b->'evidence'->0;
    IF e->>'evidence_ref' IS DISTINCT FROM expected_ref
       OR e->>'tenant_id' IS DISTINCT FROM a.tenant_id::text
       OR e->>'content_hash' IS DISTINCT FROM btrim(a.assessment_digest)
       OR e->>'verification_state' IS DISTINCT FROM 'verified'
       OR e->>'source_system' IS DISTINCT FROM 'field-management-service'
       OR e->>'evidence_type' IS DISTINCT FROM 'scouting_verification_assessment'
       OR e->>'captured_at' IS DISTINCT FROM r->>'completed_at' THEN
        RAISE EXCEPTION 'verification_delivery_evidence_binding_invalid' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS scouting_verification_delivery_insert_guard ON scouting_verification_outbox;
CREATE TRIGGER scouting_verification_delivery_insert_guard BEFORE INSERT ON scouting_verification_outbox
    FOR EACH ROW EXECUTE FUNCTION scouting_verification_delivery_insert_guard();

-- Tenant isolation, written statically so schema inventories (database_contract_graph) read it.
ALTER TABLE scouting_verification_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE scouting_verification_links FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS verification_tenant ON scouting_verification_links;
CREATE POLICY verification_tenant ON scouting_verification_links
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
REVOKE ALL ON scouting_verification_links FROM PUBLIC;
ALTER TABLE scouting_verification_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE scouting_verification_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS verification_tenant ON scouting_verification_versions;
CREATE POLICY verification_tenant ON scouting_verification_versions
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
REVOKE ALL ON scouting_verification_versions FROM PUBLIC;
ALTER TABLE scouting_verification_assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE scouting_verification_assessments FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS verification_tenant ON scouting_verification_assessments;
CREATE POLICY verification_tenant ON scouting_verification_assessments
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
REVOKE ALL ON scouting_verification_assessments FROM PUBLIC;
ALTER TABLE scouting_verification_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE scouting_verification_outbox FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS verification_tenant ON scouting_verification_outbox;
CREATE POLICY verification_tenant ON scouting_verification_outbox
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
REVOKE ALL ON scouting_verification_outbox FROM PUBLIC;
DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['scouting_verification_versions','scouting_verification_assessments'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS verification_append_only ON %I', tab);
        EXECUTE format('CREATE TRIGGER verification_append_only BEFORE UPDATE OR DELETE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION field_mgmt_append_only()', tab);
    END LOOP;
END $$;
DROP POLICY IF EXISTS verification_version_actor ON scouting_verification_versions;
CREATE POLICY verification_version_actor ON scouting_verification_versions AS RESTRICTIVE FOR INSERT
    WITH CHECK (created_by = current_setting('app.current_user_id', true));
DROP POLICY IF EXISTS verification_assessment_actor ON scouting_verification_assessments;
CREATE POLICY verification_assessment_actor ON scouting_verification_assessments AS RESTRICTIVE FOR INSERT
    WITH CHECK (reviewer = current_setting('app.current_user_id', true));
COMMENT ON TABLE scouting_verification_assessments IS
    'Explicit human judgement of an observed signal, bound to a reviewed visit; not a causal diagnosis, training label, or execution receipt.';
COMMIT;
