-- v277: a pin inspection task closes only on an approved review of the current photo evidence.
-- ════════════════════════════════════════════════════════════════════════
-- The held update_task close gate (carrier D #1439) lived in the platform's PATCH /api/v1/tasks.
-- It returns as a trigger on field_tasks, installed by field-management-service (the table's
-- owner), so it holds for every writer of the row and the platform gains no read of the hand-off
-- tables. The platform maps SH001 and SH002 below to 409 (api/routers/tasks.py); its PATCH never
-- writes source_scouting_pin_id, so SH003 is reached only by a direct writer.
--
-- field_task_inspection_close_gate (BEFORE INSERT OR UPDATE): a task is a pin inspection task when
-- the stored row or the new one names a source_scouting_pin_id. For such a task
--   * SH003 inspection_pin_immutable — once set, source_scouting_pin_id cannot be changed or
--     cleared, so a writer cannot drop the pin to escape the gate;
--   * SH001 inspection_review_required — a pin task cannot be inserted already 'completed';
-- and moving it to 'completed' needs
--   * SH001 inspection_review_required — the last hand-off event (v275) to be an approval of the
--     latest submitted evidence version (the version of the last 'submit' event, which is also the
--     newest version row of v274): approving a superseded version does not close the task; and
--   * SH002 inspection_evidence_changed — the pin's scout photo evidence now (v260) to be exactly
--     the one in the approved evidence version (v274): same evidence id and content digest, or
--     none in both. A photo added or replaced after the approval needs a new submit and approval.
-- A replay that changes nothing does not run the gate (the platform writes no unchanged row,
-- #1423), and a task that is already completed is not re-checked.
--
-- field_task_inspection_reopen (AFTER UPDATE OF status): reopening a closed pin inspection task
-- appends a 'reopen' hand-off event by the current user, so the next close needs a fresh review.
--
-- Both read and write under the caller's role and tenant (no SECURITY DEFINER). Idempotent.
BEGIN;
CREATE OR REPLACE FUNCTION field_task_inspection_close_gate() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    task_pin text;
    last_event record;
    submitted integer;
    newest integer;
    photo record;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.source_scouting_pin_id IS NOT NULL AND NEW.status = 'completed' THEN
            RAISE EXCEPTION 'inspection_review_required' USING ERRCODE = 'SH001';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.source_scouting_pin_id IS NOT NULL
       AND NEW.source_scouting_pin_id IS DISTINCT FROM OLD.source_scouting_pin_id THEN
        RAISE EXCEPTION 'inspection_pin_immutable' USING ERRCODE = 'SH003';
    END IF;
    task_pin := COALESCE(OLD.source_scouting_pin_id, NEW.source_scouting_pin_id);
    IF task_pin IS NULL OR NEW.status IS DISTINCT FROM 'completed'
       OR OLD.status IS NOT DISTINCT FROM 'completed' THEN
        RETURN NEW;
    END IF;
    SELECT h.action, h.evidence_version, v.photo_evidence_id, v.photo_content_sha256
      INTO last_event
      FROM inspection_handoffs h
      LEFT JOIN inspection_evidence_versions v
             ON v.task_id = h.task_id AND v.version = h.evidence_version
     WHERE h.tenant_id = NEW.tenant_id AND h.task_id = NEW.task_id
     ORDER BY h.revision DESC LIMIT 1;
    IF NOT FOUND OR last_event.action <> 'approve' THEN
        RAISE EXCEPTION 'inspection_review_required' USING ERRCODE = 'SH001';
    END IF;
    SELECT evidence_version INTO submitted FROM inspection_handoffs
     WHERE tenant_id = NEW.tenant_id AND task_id = NEW.task_id AND action = 'submit'
     ORDER BY revision DESC LIMIT 1;
    SELECT max(version) INTO newest FROM inspection_evidence_versions
     WHERE tenant_id = NEW.tenant_id AND task_id = NEW.task_id;
    IF last_event.evidence_version IS DISTINCT FROM submitted
       OR last_event.evidence_version IS DISTINCT FROM newest THEN
        RAISE EXCEPTION 'inspection_review_required' USING ERRCODE = 'SH001';
    END IF;
    SELECT evidence_id, content_sha256 INTO photo FROM scout_photo_evidence
     WHERE tenant_id = NEW.tenant_id AND field_id = NEW.field_id AND pin_id = task_pin;
    IF photo.evidence_id IS DISTINCT FROM last_event.photo_evidence_id
       OR photo.content_sha256::text IS DISTINCT FROM last_event.photo_content_sha256::text THEN
        RAISE EXCEPTION 'inspection_evidence_changed' USING ERRCODE = 'SH002';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS field_task_inspection_close_gate ON field_tasks;
CREATE TRIGGER field_task_inspection_close_gate BEFORE INSERT OR UPDATE ON field_tasks
    FOR EACH ROW EXECUTE FUNCTION field_task_inspection_close_gate();

CREATE OR REPLACE FUNCTION field_task_inspection_reopen() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.source_scouting_pin_id IS NULL OR OLD.status NOT IN ('completed', 'cancelled')
       OR NEW.status NOT IN ('pending', 'in_progress') THEN
        RETURN NEW;
    END IF;
    INSERT INTO inspection_handoffs
        (tenant_id, field_id, task_id, revision, action, previous_assignee, assignee, actor)
    SELECT NEW.tenant_id, NEW.field_id, NEW.task_id, COALESCE(MAX(revision), 0) + 1, 'reopen',
           COALESCE(NEW.assigned_to, ''), COALESCE(NEW.assigned_to, ''),
           current_setting('app.current_user_id', true)
      FROM inspection_handoffs WHERE tenant_id = NEW.tenant_id AND task_id = NEW.task_id;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS field_task_inspection_reopen ON field_tasks;
CREATE TRIGGER field_task_inspection_reopen AFTER UPDATE OF status ON field_tasks
    FOR EACH ROW EXECUTE FUNCTION field_task_inspection_reopen();
COMMIT;
