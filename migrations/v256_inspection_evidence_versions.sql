-- v256: bind an inspection review to the evidence version it saw.
-- Each change to a pin inspection task's photo_url or notes appends a version (never an update),
-- and submit/approve/return events name the version they refer to. Closing needs the latest
-- version to be the approved one. Idempotent: IF NOT EXISTS and catalog-checked constraints.
BEGIN;
CREATE TABLE IF NOT EXISTS inspection_evidence_versions (
    tenant_id uuid NOT NULL,
    field_id varchar(50) NOT NULL,
    task_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    photo_url text,
    notes text,
    digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
    recorded_by text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (task_id, version),
    FOREIGN KEY (tenant_id, field_id, task_id)
        REFERENCES field_tasks(tenant_id, field_id, task_id) ON DELETE RESTRICT
);
-- Leading tenant_id, so v57 adds no second index on a later MANIFEST pass (v240).
CREATE INDEX IF NOT EXISTS ix_inspection_evidence_versions_task
    ON inspection_evidence_versions (tenant_id, field_id, task_id, version);
ALTER TABLE inspection_evidence_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspection_evidence_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS evidence_read ON inspection_evidence_versions;
CREATE POLICY evidence_read ON inspection_evidence_versions FOR SELECT
    USING (tenant_id::text=current_setting('app.current_tenant', true));
DROP POLICY IF EXISTS evidence_append ON inspection_evidence_versions;
CREATE POLICY evidence_append ON inspection_evidence_versions FOR INSERT
    WITH CHECK (tenant_id::text=current_setting('app.current_tenant', true)
            AND recorded_by=current_setting('app.current_user_id', true));

ALTER TABLE inspection_handoffs ADD COLUMN IF NOT EXISTS evidence_version integer;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='inspection_handoffs'::regclass
                   AND conname='fk_inspection_handoff_evidence') THEN
        ALTER TABLE inspection_handoffs ADD CONSTRAINT fk_inspection_handoff_evidence
            FOREIGN KEY (task_id, evidence_version)
            REFERENCES inspection_evidence_versions(task_id, version);
    END IF;
    -- Reviews recorded before v256 carry no version; they stay valid, new ones must name one.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='inspection_handoffs'::regclass
                   AND conname='inspection_handoff_evidence_ck') THEN
        ALTER TABLE inspection_handoffs ADD CONSTRAINT inspection_handoff_evidence_ck CHECK (
            (action IN ('submit','approve','return')) = (evidence_version IS NOT NULL)) NOT VALID;
    END IF;
END $$;
COMMIT;
