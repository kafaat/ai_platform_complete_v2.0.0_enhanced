-- v275: the hand-off log of a pin inspection task, owned by field-management-service.
-- ════════════════════════════════════════════════════════════════════════
-- Rebuilds the held v248 + v254 + v256 hand-off shape (carrier D #1439) as one new table on main:
--   accept   — the assignee takes the task (actor = assignee, no reason);
--   reassign — a supervisor moves it to someone else, with a reason;
--   submit   — the assignee records the finding, bound to an evidence version (v274);
--   approve / return — someone other than the assignee reviews that exact version;
--   reopen   — a closed inspection task was reopened (written by v277's trigger on field_tasks).
-- One row per revision; revisions are dense from 1, so expected_revision names a command slot and
-- an exact replay is answered with the current state. Append-only (no UPDATE or DELETE).
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

COMMENT ON TABLE inspection_handoffs IS
    'Append-only hand-off and review log of a pin inspection task (v275, owner field-management-service).';
COMMIT;
