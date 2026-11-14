-- v274: the evidence an inspection review is bound to (gap P3), owned by field-management-service.
-- ════════════════════════════════════════════════════════════════════════
-- Owner decision (2026-11-14): the pin inspection flow that carrier D #1439 held back returns under
-- field-management-service, the owner of field_tasks. The held v256 hashed field_tasks.photo_url.
-- On main the observation photo has one source of truth: scout_photo_evidence (v260, owned by
-- scout-ingest), immutable and one row per (tenant, field, pin). So a version names that record,
-- by id and content digest, never a URL; field_tasks.photo_url plays no part.
--
-- A version is appended (never updated) when the inspector submits a finding. It carries the photo
-- evidence present at that moment (or none) and the inspector's notes. digest is
-- sha256(json [photo_evidence_id, photo_content_sha256, notes]), computed by the service
-- (services/field-management-service/task_inspection.py:evidence_digest) and checked here.
-- An approval (v275) names one version; v277 refuses to close the task when the pin's current
-- photo evidence is no longer the one in the approved version.
--
-- The guard trigger checks what a foreign key cannot: the task is a pin inspection task, the pin is
-- the task's pin, and a named photo is that pin's evidence row with that exact digest.
--
-- Idempotent on a re-applied MANIFEST: IF NOT EXISTS, DROP ... IF EXISTS, CREATE OR REPLACE.
-- Leading tenant_id on the index, so v57 adds no second index on a later pass (v240).
BEGIN;
CREATE TABLE IF NOT EXISTS inspection_evidence_versions (
    tenant_id uuid NOT NULL,
    field_id varchar(50) NOT NULL,
    task_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    pin_id text NOT NULL,
    photo_evidence_id uuid REFERENCES scout_photo_evidence (evidence_id) ON DELETE RESTRICT,
    photo_content_sha256 char(64) CHECK (photo_content_sha256 ~ '^[0-9a-f]{64}$'),
    notes text CHECK (notes IS NULL OR length(notes) <= 4000),
    digest char(64) NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
    recorded_by text NOT NULL CHECK (length(btrim(recorded_by)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (task_id, version),
    CONSTRAINT inspection_evidence_photo_pair_ck
        CHECK ((photo_evidence_id IS NULL) = (photo_content_sha256 IS NULL)),
    CONSTRAINT inspection_evidence_task_fk FOREIGN KEY (tenant_id, field_id, task_id)
        REFERENCES field_tasks (tenant_id, field_id, task_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_inspection_evidence_versions_task
    ON inspection_evidence_versions (tenant_id, field_id, task_id, version);

ALTER TABLE inspection_evidence_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspection_evidence_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS evidence_read ON inspection_evidence_versions;
CREATE POLICY evidence_read ON inspection_evidence_versions FOR SELECT
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
DROP POLICY IF EXISTS evidence_append ON inspection_evidence_versions;
CREATE POLICY evidence_append ON inspection_evidence_versions FOR INSERT
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')
            AND recorded_by = current_setting('app.current_user_id', true));

CREATE OR REPLACE FUNCTION field_mgmt_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = '55000';
END $$;
DROP TRIGGER IF EXISTS inspection_evidence_versions_append_only ON inspection_evidence_versions;
CREATE TRIGGER inspection_evidence_versions_append_only
    BEFORE UPDATE OR DELETE ON inspection_evidence_versions
    FOR EACH ROW EXECUTE FUNCTION field_mgmt_append_only();

CREATE OR REPLACE FUNCTION inspection_evidence_version_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    task_pin text;
    photo_sha text;
BEGIN
    SELECT source_scouting_pin_id INTO task_pin FROM field_tasks
     WHERE tenant_id = NEW.tenant_id AND field_id = NEW.field_id AND task_id = NEW.task_id;
    IF task_pin IS NULL OR task_pin <> NEW.pin_id THEN
        RAISE EXCEPTION 'inspection evidence must name the task''s own scouting pin'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.digest <> encode(sha256(convert_to(
            coalesce(NEW.photo_evidence_id::text, '') || '|' || coalesce(NEW.photo_content_sha256, '')
            || '|' || coalesce(NEW.notes, ''), 'UTF8')), 'hex') THEN
        RAISE EXCEPTION 'inspection evidence digest does not match its content' USING ERRCODE = '23514';
    END IF;
    IF NEW.photo_evidence_id IS NOT NULL THEN
        SELECT content_sha256 INTO photo_sha FROM scout_photo_evidence
         WHERE evidence_id = NEW.photo_evidence_id AND tenant_id = NEW.tenant_id
           AND field_id = NEW.field_id AND pin_id = NEW.pin_id;
        IF photo_sha IS NULL OR photo_sha <> NEW.photo_content_sha256 THEN
            RAISE EXCEPTION 'inspection evidence photo is not this pin''s scout photo evidence'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS inspection_evidence_version_guard ON inspection_evidence_versions;
CREATE TRIGGER inspection_evidence_version_guard
    BEFORE INSERT ON inspection_evidence_versions
    FOR EACH ROW EXECUTE FUNCTION inspection_evidence_version_guard();

COMMENT ON TABLE inspection_evidence_versions IS
    'Append-only evidence versions of a pin inspection (v274, owner field-management-service); a photo is named by its scout_photo_evidence id and content digest, never a URL.';
COMMIT;
