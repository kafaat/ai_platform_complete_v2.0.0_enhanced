-- v275: the hand-off log of a pin inspection task, owned by field-management-service.
-- ════════════════════════════════════════════════════════════════════════
-- Rebuilds the held v248 + v254 + v256 hand-off shape (carrier D #1439) as one new table on main:
--   accept   — the assignee takes the task (actor = assignee, no reason);
--   reassign — a supervisor moves it to someone else, with a reason;
--   submit   — the assignee records the finding, bound to an evidence version (v274);
--   approve / return — someone other than the assignee reviews that exact version;
--   reopen   — a closed inspection task was reopened (written by v277's trigger on field_tasks).
-- One row per revision; revisions are dense from 1, so expected_revision names a command slot and
-- an exact replay is answered with the current state. The inspection_handoff_revision_guard trigger
-- holds that for every writer: a row whose revision is not the task's previous revision + 1 is
-- refused (SH004 inspection_revision_gap). Append-only (no UPDATE or DELETE).
--
-- The CHECK below only compares a row with itself, so a writer could name any assignee it likes
-- (an inspector approving their own work by declaring the reviewer the assignee). The
-- inspection_handoff_chain_guard trigger ties every row to the task: previous_assignee must be the
-- assignee of the prior event (for the first event, the task's initial assignee, else its current
-- one) and assignee must be field_tasks.assigned_to now (a reassign updates the task first), or
-- SH006 inspection_handoff_chain_broken; an approve or return by the user who submitted or
-- recorded that evidence version is SH007 inspection_self_review.
-- Known limit (systemic, not solved here): the actor is app.current_user_id, a GUC the shared app
-- role can set, so a writer holding that role can still act under another user's id.
--
-- The INSERT policy binds actor to app.current_user_id: a row can only be written by the user the
-- connection was opened for. Idempotent on a re-applied MANIFEST.
BEGIN;
CREATE TABLE IF NOT EXISTS inspection_handoffs (
    tenant_id uuid NOT NULL,
    field_id varchar(50) NOT NULL,
    task_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    action text NOT NULL
        CHECK (action IN ('accept', 'reassign', 'submit', 'approve', 'return', 'reopen')),
    previous_assignee text NOT NULL,
    assignee text NOT NULL,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    reason text,
    evidence_version integer,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (task_id, revision),
    CONSTRAINT inspection_handoff_task_fk FOREIGN KEY (tenant_id, field_id, task_id)
        REFERENCES field_tasks (tenant_id, field_id, task_id) ON DELETE RESTRICT,
    CONSTRAINT inspection_handoff_evidence_fk FOREIGN KEY (task_id, evidence_version)
        REFERENCES inspection_evidence_versions (task_id, version) ON DELETE RESTRICT,
    CONSTRAINT inspection_handoff_event_ck CHECK (
        (action = 'accept' AND actor = assignee AND previous_assignee = assignee AND reason IS NULL)
     OR (action = 'reopen' AND previous_assignee = assignee AND reason IS NULL)
     OR (action = 'reassign' AND previous_assignee <> assignee
         AND reason IS NOT NULL AND length(btrim(reason)) BETWEEN 1 AND 500)
     OR (action IN ('submit', 'approve', 'return') AND previous_assignee = assignee
         AND (actor = assignee) = (action = 'submit')
         AND reason IS NOT NULL AND length(btrim(reason)) BETWEEN 1 AND 2000)
    ),
    CONSTRAINT inspection_handoff_evidence_ck CHECK (
        (action IN ('submit', 'approve', 'return')) = (evidence_version IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS ix_inspection_handoffs_task
    ON inspection_handoffs (tenant_id, field_id, task_id, revision);

ALTER TABLE inspection_handoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspection_handoffs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS handoff_read ON inspection_handoffs;
CREATE POLICY handoff_read ON inspection_handoffs FOR SELECT
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
DROP POLICY IF EXISTS handoff_append ON inspection_handoffs;
CREATE POLICY handoff_append ON inspection_handoffs FOR INSERT
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')
            AND actor = current_setting('app.current_user_id', true));

DROP TRIGGER IF EXISTS inspection_handoffs_append_only ON inspection_handoffs;
CREATE TRIGGER inspection_handoffs_append_only
    BEFORE UPDATE OR DELETE ON inspection_handoffs
    FOR EACH ROW EXECUTE FUNCTION field_mgmt_append_only();

CREATE OR REPLACE FUNCTION inspection_handoff_revision_guard() RETURNS trigger LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF NEW.revision IS DISTINCT FROM (
        SELECT COALESCE(max(revision), 0) + 1 FROM public.inspection_handoffs
         WHERE tenant_id = NEW.tenant_id AND task_id = NEW.task_id) THEN
        RAISE EXCEPTION 'inspection_revision_gap' USING ERRCODE = 'SH004';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS inspection_handoff_revision_guard ON inspection_handoffs;
CREATE TRIGGER inspection_handoff_revision_guard BEFORE INSERT ON inspection_handoffs
    FOR EACH ROW EXECUTE FUNCTION inspection_handoff_revision_guard();

CREATE OR REPLACE FUNCTION inspection_handoff_chain_guard() RETURNS trigger LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    task record;
    prior text;
BEGIN
    -- FOR UPDATE serialises a hand-off with a concurrent close of the same task (review round 3
    -- of #1460): whichever commits first, the other sees it. A closed task takes only 'reopen'.
    SELECT assigned_to, inspection_initial_assignee, status INTO task FROM public.field_tasks
     WHERE tenant_id = NEW.tenant_id AND field_id = NEW.field_id AND task_id = NEW.task_id
       FOR UPDATE;
    IF lower(btrim(COALESCE(task.status, ''))) = 'completed' AND NEW.action <> 'reopen' THEN
        RAISE EXCEPTION 'inspection_task_closed' USING ERRCODE = 'SH008';
    END IF;
    SELECT assignee INTO prior FROM public.inspection_handoffs
     WHERE tenant_id = NEW.tenant_id AND task_id = NEW.task_id
     ORDER BY revision DESC LIMIT 1;
    IF NOT FOUND THEN
        prior := COALESCE(task.inspection_initial_assignee, task.assigned_to, '');
    END IF;
    IF NEW.previous_assignee IS DISTINCT FROM prior
       OR NEW.assignee IS DISTINCT FROM COALESCE(task.assigned_to, '') THEN
        RAISE EXCEPTION 'inspection_handoff_chain_broken' USING ERRCODE = 'SH006';
    END IF;
    IF NEW.action IN ('approve', 'return') AND (
        EXISTS (SELECT 1 FROM public.inspection_handoffs
                 WHERE tenant_id = NEW.tenant_id AND task_id = NEW.task_id AND action = 'submit'
                   AND evidence_version = NEW.evidence_version AND actor = NEW.actor)
        OR EXISTS (SELECT 1 FROM public.inspection_evidence_versions
                    WHERE tenant_id = NEW.tenant_id AND task_id = NEW.task_id
                      AND version = NEW.evidence_version AND recorded_by = NEW.actor)) THEN
        RAISE EXCEPTION 'inspection_self_review' USING ERRCODE = 'SH007';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS inspection_handoff_chain_guard ON inspection_handoffs;
CREATE TRIGGER inspection_handoff_chain_guard BEFORE INSERT ON inspection_handoffs
    FOR EACH ROW EXECUTE FUNCTION inspection_handoff_chain_guard();

COMMENT ON TABLE inspection_handoffs IS
    'Append-only hand-off and review log of a pin inspection task (v275, owner field-management-service).';
COMMIT;
