BEGIN;
CREATE TABLE IF NOT EXISTS inspection_handoffs (
    tenant_id uuid NOT NULL,
    field_id varchar(50) NOT NULL,
    task_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    action text NOT NULL CHECK (action IN ('accept','reassign')),
    previous_assignee text NOT NULL,
    assignee text NOT NULL,
    actor text NOT NULL,
    reason text,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (task_id, revision),
    FOREIGN KEY (tenant_id, field_id, task_id)
        REFERENCES field_tasks(tenant_id, field_id, task_id) ON DELETE RESTRICT,
    CHECK ((action='accept' AND actor=assignee AND previous_assignee=assignee AND reason IS NULL)
        OR (action='reassign' AND previous_assignee<>assignee AND length(btrim(reason))>0 AND reason IS NOT NULL))
);
-- Leading tenant_id: the read path filters (tenant, field, task) in revision order, and v57 would
-- otherwise add idx_inspection_handoffs_tenant on a second MANIFEST pass (v240 path-dependence).
CREATE INDEX IF NOT EXISTS ix_inspection_handoffs_task
    ON inspection_handoffs (tenant_id, field_id, task_id, revision);
ALTER TABLE inspection_handoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspection_handoffs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS handoff_read ON inspection_handoffs;
CREATE POLICY handoff_read ON inspection_handoffs FOR SELECT
    USING (tenant_id::text=current_setting('app.current_tenant', true));
DROP POLICY IF EXISTS handoff_append ON inspection_handoffs;
CREATE POLICY handoff_append ON inspection_handoffs FOR INSERT
    WITH CHECK (tenant_id::text=current_setting('app.current_tenant', true)
            AND actor=current_setting('app.current_user_id', true));
COMMIT;
