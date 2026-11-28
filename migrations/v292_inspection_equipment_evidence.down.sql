-- Refuse destructive rollback once an equipment declaration has been recorded.
BEGIN;
-- Bound the exclusive table lock wait; a busy store must fail without partial DDL.
SET LOCAL lock_timeout = '15s';
SET LOCAL row_security = off;
LOCK TABLE inspection_evidence_versions IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM inspection_evidence_versions WHERE equipment_id IS NOT NULL) THEN
        RAISE EXCEPTION 'cannot discard immutable equipment evidence';
    END IF;
END $$;
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
            coalesce(NEW.photo_evidence_id::text, '') || '|' || coalesce(NEW.photo_content_sha256, '')
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
ALTER TABLE inspection_evidence_versions DROP COLUMN equipment_id;
COMMIT;
