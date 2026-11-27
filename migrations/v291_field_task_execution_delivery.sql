-- v291: owner-local task delivery and reviewed inspection completion references.
-- The request/plan/authorization identifiers are typed external references, not cross-owner
-- foreign keys. field-management-service fetches and validates their authoritative lineage
-- before creating the task and link in one transaction. No delivery token is persisted.
--
-- A confirmation is an immutable, dated inspection snapshot, not an upstream outcome. A newer
-- snapshot may follow a stale one until an outcome receipt is stored. The decision owner must
-- read the current proof from field-management immediately before accepting the outcome. This
-- does not freeze reopening/photos or claim a linearizable transaction across the two owners.
-- Outcome receipts record only the matching authoritative decision response, after its commit.
--
-- Requires v245/v246/v260/v274/v275/v277/v282. New tables are owned by field-management-service.
-- Row guards run as the caller, with FORCE RLS and transaction-local tenant/user identity.
BEGIN;
SET LOCAL lock_timeout = '15s';

CREATE TABLE IF NOT EXISTS field_task_execution_links (
    tenant_id uuid NOT NULL,
    execution_request_id text NOT NULL CHECK (btrim(execution_request_id) <> ''),
    task_id uuid NOT NULL,
    field_id varchar(50) NOT NULL,
    pin_id text NOT NULL,
    operation_type text NOT NULL DEFAULT 'field_inspection'
        CHECK (operation_type = 'field_inspection'),
    decision_id text NOT NULL CHECK (btrim(decision_id) <> ''),
    execution_plan_id text NOT NULL CHECK (btrim(execution_plan_id) <> ''),
    dispatch_authorization_id text NOT NULL CHECK (btrim(dispatch_authorization_id) <> ''),
    correlation_id uuid NOT NULL,
    assigned_to text NOT NULL CHECK (btrim(assigned_to) <> ''),
    due_at timestamptz NOT NULL,
    priority smallint NOT NULL CHECK (priority BETWEEN 1 AND 5),
    request_digest char(64) NOT NULL CHECK (request_digest::text ~ '^[0-9a-f]{64}$'),
    adapter_id text NOT NULL CHECK (btrim(adapter_id) <> ''),
    receipt_id text NOT NULL CHECK (btrim(receipt_id) <> ''),
    receipt_payload jsonb NOT NULL CHECK (jsonb_typeof(receipt_payload) = 'object')
        CHECK (NOT jsonb_path_exists(receipt_payload, '$.**.delivery_token')),
    received_by text NOT NULL CHECK (btrim(received_by) <> ''),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, execution_request_id),
    UNIQUE (tenant_id, task_id),
    UNIQUE (tenant_id, receipt_id),
    UNIQUE (tenant_id, field_id, task_id, execution_request_id, pin_id),
    FOREIGN KEY (tenant_id, field_id, task_id)
        REFERENCES field_tasks (tenant_id, field_id, task_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, field_id, pin_id)
        REFERENCES scouting_pins (tenant_id, field_id, pin_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_field_task_execution_links_field
    ON field_task_execution_links (tenant_id, field_id, created_at DESC);

CREATE TABLE IF NOT EXISTS field_task_execution_confirmations (
    confirmation_id text PRIMARY KEY CHECK (btrim(confirmation_id) <> ''),
    tenant_id uuid NOT NULL,
    execution_request_id text NOT NULL,
    task_id uuid NOT NULL,
    field_id varchar(50) NOT NULL,
    pin_id text NOT NULL,
    handoff_revision integer NOT NULL CHECK (handoff_revision > 0),
    evidence_version integer NOT NULL CHECK (evidence_version > 0),
    evidence_digest char(64) NOT NULL CHECK (evidence_digest::text ~ '^[0-9a-f]{64}$'),
    photo_evidence_id uuid,
    photo_content_sha256 char(64) CHECK (photo_content_sha256::text ~ '^[0-9a-f]{64}$'),
    inspector_id text NOT NULL CHECK (btrim(inspector_id) <> ''),
    reviewer_id text NOT NULL CHECK (btrim(reviewer_id) <> ''),
    verified_by text NOT NULL CHECK (btrim(verified_by) <> ''),
    evidence_snapshot_id text NOT NULL CHECK (btrim(evidence_snapshot_id) <> ''),
    idempotency_key text NOT NULL CHECK (btrim(idempotency_key) <> ''),
    actual jsonb NOT NULL CHECK (jsonb_typeof(actual) = 'object'),
    metrics jsonb NOT NULL CHECK (jsonb_typeof(metrics) = 'object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((photo_evidence_id IS NULL) = (photo_content_sha256 IS NULL)),
    CHECK (reviewer_id = verified_by AND reviewer_id <> inspector_id),
    UNIQUE (tenant_id, confirmation_id),
    UNIQUE (tenant_id, idempotency_key),
    UNIQUE (tenant_id, execution_request_id, handoff_revision, evidence_version),
    UNIQUE (tenant_id, field_id, task_id, execution_request_id, confirmation_id),
    FOREIGN KEY (tenant_id, field_id, task_id, execution_request_id, pin_id)
        REFERENCES field_task_execution_links
            (tenant_id, field_id, task_id, execution_request_id, pin_id) ON DELETE RESTRICT,
    FOREIGN KEY (task_id, evidence_version)
        REFERENCES inspection_evidence_versions (task_id, version) ON DELETE RESTRICT,
    FOREIGN KEY (task_id, handoff_revision)
        REFERENCES inspection_handoffs (task_id, revision) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_field_task_execution_confirmations_task
    ON field_task_execution_confirmations (tenant_id, task_id, created_at DESC);

CREATE TABLE IF NOT EXISTS field_task_execution_outcome_receipts (
    tenant_id uuid NOT NULL,
    confirmation_id text NOT NULL,
    execution_request_id text NOT NULL,
    task_id uuid NOT NULL,
    field_id varchar(50) NOT NULL,
    outcome_id text NOT NULL CHECK (btrim(outcome_id) <> ''),
    upstream_result jsonb NOT NULL CHECK (jsonb_typeof(upstream_result) = 'object')
        CHECK (NOT jsonb_path_exists(upstream_result, '$.**.delivery_token')),
    received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, execution_request_id),
    UNIQUE (tenant_id, task_id),
    UNIQUE (tenant_id, confirmation_id),
    UNIQUE (tenant_id, outcome_id),
    FOREIGN KEY (tenant_id, field_id, task_id, execution_request_id, confirmation_id)
        REFERENCES field_task_execution_confirmations
            (tenant_id, field_id, task_id, execution_request_id, confirmation_id)
        ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION field_task_execution_link_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE t record;
BEGIN
    SELECT task_type, source_scouting_pin_id, anomaly_ref, assigned_to,
           inspection_initial_assignee, inspection_assigned_by, inspection_due_at, priority, status
      INTO t FROM public.field_tasks
     WHERE tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND task_id=NEW.task_id
       FOR UPDATE;
    IF NOT FOUND OR t.task_type IS DISTINCT FROM 'scouting'
       OR t.source_scouting_pin_id IS DISTINCT FROM NEW.pin_id OR t.anomaly_ref IS NOT NULL
       OR t.assigned_to IS DISTINCT FROM NEW.assigned_to
       OR t.inspection_initial_assignee IS DISTINCT FROM NEW.assigned_to
       OR t.inspection_assigned_by IS DISTINCT FROM NEW.received_by
       OR t.inspection_due_at IS DISTINCT FROM NEW.due_at OR t.priority IS DISTINCT FROM NEW.priority
       OR lower(btrim(coalesce(t.status, ''))) <> 'pending'
       OR EXISTS (SELECT 1 FROM public.inspection_handoffs
                   WHERE tenant_id=NEW.tenant_id AND task_id=NEW.task_id) THEN
        RAISE EXCEPTION 'execution_link_task_binding_invalid' USING ERRCODE='23514';
    END IF;
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS field_task_execution_link_guard ON field_task_execution_links;
CREATE TRIGGER field_task_execution_link_guard BEFORE INSERT ON field_task_execution_links
    FOR EACH ROW EXECUTE FUNCTION field_task_execution_link_guard();

CREATE OR REPLACE FUNCTION field_task_execution_confirmation_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE t record; h record; v record; s record; p record; newest integer; reopened integer;
BEGIN
    -- The same task row lock used by v275/v277 serializes handoffs, close and reopen. Photo
    -- evidence has a different owner: read its current row without granting a cross-owner UPDATE.
    SELECT source_scouting_pin_id, task_type, anomaly_ref, status INTO t FROM public.field_tasks
     WHERE tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND task_id=NEW.task_id FOR UPDATE;
    IF NOT FOUND OR t.source_scouting_pin_id IS DISTINCT FROM NEW.pin_id
       OR t.task_type IS DISTINCT FROM 'scouting' OR t.anomaly_ref IS NOT NULL
       OR lower(btrim(coalesce(t.status, ''))) <> 'completed' THEN
        RAISE EXCEPTION 'execution_confirmation_task_not_completed' USING ERRCODE='23514';
    END IF;
    IF EXISTS (SELECT 1 FROM public.field_task_execution_outcome_receipts
                WHERE tenant_id=NEW.tenant_id AND execution_request_id=NEW.execution_request_id) THEN
        RAISE EXCEPTION 'execution_outcome_already_recorded' USING ERRCODE='23514';
    END IF;
    SELECT * INTO h FROM public.inspection_handoffs
     WHERE tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND task_id=NEW.task_id
     ORDER BY revision DESC LIMIT 1;
    SELECT * INTO s FROM public.inspection_handoffs
     WHERE tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND task_id=NEW.task_id
       AND action='submit' ORDER BY revision DESC LIMIT 1;
    SELECT max(revision) INTO reopened FROM public.inspection_handoffs
     WHERE tenant_id=NEW.tenant_id AND task_id=NEW.task_id AND action='reopen';
    SELECT max(version) INTO newest FROM public.inspection_evidence_versions
     WHERE tenant_id=NEW.tenant_id AND task_id=NEW.task_id;
    SELECT * INTO v FROM public.inspection_evidence_versions
     WHERE tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND task_id=NEW.task_id
       AND version=NEW.evidence_version;
    SELECT evidence_id, content_sha256 INTO p FROM public.scout_photo_evidence
     WHERE tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND pin_id=NEW.pin_id;
    IF h.action IS DISTINCT FROM 'approve' OR h.revision IS DISTINCT FROM NEW.handoff_revision
       OR h.evidence_version IS DISTINCT FROM NEW.evidence_version
       OR h.revision <= coalesce(reopened, 0)
       OR s.evidence_version IS DISTINCT FROM NEW.evidence_version
       OR s.revision <= coalesce(reopened, 0) OR s.revision >= h.revision
       OR newest IS DISTINCT FROM NEW.evidence_version
       OR v.version IS NULL OR v.pin_id IS DISTINCT FROM NEW.pin_id
       OR v.digest IS DISTINCT FROM NEW.evidence_digest
       OR v.photo_evidence_id IS DISTINCT FROM NEW.photo_evidence_id
       OR v.photo_content_sha256 IS DISTINCT FROM NEW.photo_content_sha256
       OR p.evidence_id IS DISTINCT FROM NEW.photo_evidence_id
       OR p.content_sha256 IS DISTINCT FROM NEW.photo_content_sha256
       OR s.actor IS DISTINCT FROM NEW.inspector_id
       OR v.recorded_by IS DISTINCT FROM NEW.inspector_id
       OR h.actor IS DISTINCT FROM NEW.reviewer_id
       OR h.actor IS DISTINCT FROM NEW.verified_by
       OR h.actor IS NOT DISTINCT FROM s.actor OR h.actor IS NOT DISTINCT FROM v.recorded_by THEN
        RAISE EXCEPTION 'execution_confirmation_requires_current_independent_review'
            USING ERRCODE='23514';
    END IF;
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS field_task_execution_confirmation_guard ON field_task_execution_confirmations;
CREATE TRIGGER field_task_execution_confirmation_guard BEFORE INSERT ON field_task_execution_confirmations
    FOR EACH ROW EXECUTE FUNCTION field_task_execution_confirmation_guard();

CREATE OR REPLACE FUNCTION field_task_execution_outcome_receipt_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE c record; l record; r jsonb;
BEGIN
    -- Serialize the terminal local receipt with new confirmation snapshots. An upstream outcome
    -- is historical once committed; a later reopen must not erase or rewrite its receipt.
    PERFORM 1 FROM public.field_tasks WHERE tenant_id=NEW.tenant_id
       AND field_id=NEW.field_id AND task_id=NEW.task_id FOR UPDATE;
    SELECT * INTO c FROM public.field_task_execution_confirmations
     WHERE tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND task_id=NEW.task_id
       AND execution_request_id=NEW.execution_request_id AND confirmation_id=NEW.confirmation_id;
    SELECT * INTO l FROM public.field_task_execution_links
     WHERE tenant_id=NEW.tenant_id AND field_id=NEW.field_id AND task_id=NEW.task_id
       AND execution_request_id=NEW.execution_request_id;
    r := NEW.upstream_result;
    IF c.confirmation_id IS NULL OR l.execution_request_id IS NULL
       OR r->>'status' IS DISTINCT FROM 'ok'
       OR r->'persisted' IS DISTINCT FROM 'true'::jsonb
       OR r->'authoritative' IS DISTINCT FROM 'true'::jsonb
       OR r->>'outcome_id' IS DISTINCT FROM NEW.outcome_id
       OR r->>'execution_request_id' IS DISTINCT FROM NEW.execution_request_id
       OR r->>'execution_plan_id' IS DISTINCT FROM l.execution_plan_id
       OR r->>'dispatch_authorization_id' IS DISTINCT FROM l.dispatch_authorization_id
       OR r->>'decision_id' IS DISTINCT FROM l.decision_id
       OR r->>'receipt_id' IS DISTINCT FROM l.receipt_id
       OR r->>'verification_state' IS DISTINCT FROM 'verified_success'
       OR r->'success' IS DISTINCT FROM 'true'::jsonb
       OR r->>'evidence_snapshot_id' IS DISTINCT FROM c.evidence_snapshot_id
       OR r->>'verified_by' IS DISTINCT FROM c.verified_by
       OR nullif(r->>'verified_at', '') IS NULL THEN
        RAISE EXCEPTION 'execution_outcome_receipt_binding_invalid' USING ERRCODE='23514';
    END IF;
    NEW.received_at := clock_timestamp();
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS field_task_execution_outcome_receipt_guard ON field_task_execution_outcome_receipts;
CREATE TRIGGER field_task_execution_outcome_receipt_guard BEFORE INSERT ON field_task_execution_outcome_receipts
    FOR EACH ROW EXECUTE FUNCTION field_task_execution_outcome_receipt_guard();

ALTER TABLE field_task_execution_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_task_execution_links FORCE ROW LEVEL SECURITY;
ALTER TABLE field_task_execution_confirmations ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_task_execution_confirmations FORCE ROW LEVEL SECURITY;
ALTER TABLE field_task_execution_outcome_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_task_execution_outcome_receipts FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS execution_link_read ON field_task_execution_links;
CREATE POLICY execution_link_read ON field_task_execution_links FOR SELECT
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
DROP POLICY IF EXISTS execution_link_append ON field_task_execution_links;
CREATE POLICY execution_link_append ON field_task_execution_links FOR INSERT
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')
        AND received_by = current_setting('app.current_user_id', true));
DROP POLICY IF EXISTS execution_confirmation_read ON field_task_execution_confirmations;
CREATE POLICY execution_confirmation_read ON field_task_execution_confirmations FOR SELECT
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
DROP POLICY IF EXISTS execution_confirmation_append ON field_task_execution_confirmations;
CREATE POLICY execution_confirmation_append ON field_task_execution_confirmations FOR INSERT
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')
        AND verified_by = current_setting('app.current_user_id', true));
DROP POLICY IF EXISTS execution_outcome_receipt_read ON field_task_execution_outcome_receipts;
CREATE POLICY execution_outcome_receipt_read ON field_task_execution_outcome_receipts FOR SELECT
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
DROP POLICY IF EXISTS execution_outcome_receipt_append ON field_task_execution_outcome_receipts;
CREATE POLICY execution_outcome_receipt_append ON field_task_execution_outcome_receipts FOR INSERT
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

-- Triggers reject mutation even for a role with table DML grants. No mutation RLS policies
-- exist; an ordinary application role sees zero rows for UPDATE/DELETE, and TRUNCATE fails.
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['field_task_execution_links', 'field_task_execution_confirmations',
                            'field_task_execution_outcome_receipts'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS execution_append_only ON public.%I', t);
        EXECUTE format('CREATE TRIGGER execution_append_only BEFORE UPDATE OR DELETE ON public.%I '
                       'FOR EACH ROW EXECUTE FUNCTION public.field_mgmt_append_only()', t);
        EXECUTE format('DROP TRIGGER IF EXISTS execution_no_truncate ON public.%I', t);
        EXECUTE format('CREATE TRIGGER execution_no_truncate BEFORE TRUNCATE ON public.%I '
                       'FOR EACH STATEMENT EXECUTE FUNCTION public.field_mgmt_append_only()', t);
    END LOOP;
END $$;

COMMENT ON TABLE field_task_execution_links IS
    'Immutable owner-local binding from a validated field_inspection execution request to its newly created pin inspection task; contains no delivery token.';
COMMENT ON TABLE field_task_execution_confirmations IS
    'Append-only dated proof of a completed inspection with current independently approved evidence at insertion; revalidate current proof over the owner API before an upstream outcome.';
COMMENT ON TABLE field_task_execution_outcome_receipts IS
    'Append-only matching authoritative decision outcome acknowledgement; a confirmation alone is not a recorded outcome.';
COMMIT;
