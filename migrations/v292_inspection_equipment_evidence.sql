-- v292: optional equipment declaration on the field-management-owned immutable evidence.
-- This does not certify the equipment, authorize maintenance, or grant cross-domain writes.
-- Old digests remain valid; non-null declarations are bound by the version digest.
BEGIN;
-- Bound the exclusive table lock wait; a busy store must fail without partial DDL.
SET LOCAL lock_timeout = '15s';
ALTER TABLE inspection_evidence_versions ADD COLUMN IF NOT EXISTS equipment_id varchar(50)
    CHECK (equipment_id IS NULL OR equipment_id ~ '^[A-Za-z0-9_-]{1,50}$');
CREATE OR REPLACE FUNCTION inspection_evidence_version_guard() RETURNS trigger LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    task_pin text;
    photo_sha text;
BEGIN
    SELECT source_scouting_pin_id INTO task_pin FROM public.field_tasks
     WHERE tenant_id = NEW.tenant_id AND field_id = NEW.field_id AND task_id = NEW.task_id;
    IF task_pin IS NULL OR task_pin <> NEW.pin_id THEN
        RAISE EXCEPTION 'inspection evidence must name the task''s own scouting pin'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.digest <> encode(sha256(convert_to(
            CASE WHEN NEW.equipment_id IS NULL THEN ''
                 ELSE 'equipment:' || NEW.equipment_id || '|' END
            || coalesce(NEW.photo_evidence_id::text, '') || '|' || coalesce(NEW.photo_content_sha256, '')
            || '|' || coalesce(NEW.notes, ''), 'UTF8')), 'hex') THEN
        RAISE EXCEPTION 'inspection evidence digest does not match its content' USING ERRCODE = '23514';
    END IF;
    IF NEW.photo_evidence_id IS NOT NULL THEN
        SELECT content_sha256 INTO photo_sha FROM public.scout_photo_evidence
         WHERE evidence_id = NEW.photo_evidence_id AND tenant_id = NEW.tenant_id
           AND field_id = NEW.field_id AND pin_id = NEW.pin_id;
        IF photo_sha IS NULL OR photo_sha <> NEW.photo_content_sha256 THEN
            RAISE EXCEPTION 'inspection evidence photo is not this pin''s scout photo evidence'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
COMMIT;
