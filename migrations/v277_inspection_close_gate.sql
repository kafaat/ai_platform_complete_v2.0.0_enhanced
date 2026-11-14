-- v277: a pin inspection task closes only on an approved review of the current photo evidence.
-- ════════════════════════════════════════════════════════════════════════
-- The held update_task close gate (carrier D #1439) lived in the platform's PATCH /api/v1/tasks.
-- It returns as a trigger on field_tasks, installed by field-management-service (the table's
-- owner), so it holds for every writer of the row and the platform gains no read of the hand-off
-- tables. The platform maps the two SQLSTATEs below to 409 (api/routers/tasks.py).
--
-- field_task_inspection_close_gate (BEFORE UPDATE OF status): moving a task that has a
-- source_scouting_pin_id to 'completed' needs
--   * SH001 inspection_review_required — the last hand-off event (v275) to be an approval; and
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
    last_event record;
    photo record;
BEGIN
    IF NEW.source_scouting_pin_id IS NULL OR NEW.status IS DISTINCT FROM 'completed'
       OR OLD.status IS NOT DISTINCT FROM 'completed' THEN
        RETURN NEW;
    END IF;
    SELECT h.action, v.photo_evidence_id, v.photo_content_sha256 INTO last_event
      FROM inspection_handoffs h
      LEFT JOIN inspection_evidence_versions v
             ON v.task_id = h.task_id AND v.version = h.evidence_version
     WHERE h.tenant_id = NEW.tenant_id AND h.task_id = NEW.task_id
     ORDER BY h.revision DESC LIMIT 1;
    IF NOT FOUND OR last_event.action <> 'approve' THEN
        RAISE EXCEPTION 'inspection_review_required' USING ERRCODE = 'SH001';
    END IF;
    SELECT evidence_id, content_sha256 INTO photo FROM scout_photo_evidence
     WHERE tenant_id = NEW.tenant_id AND field_id = NEW.field_id
       AND pin_id = NEW.source_scouting_pin_id;
    IF photo.evidence_id IS DISTINCT FROM last_event.photo_evidence_id
       OR photo.content_sha256::text IS DISTINCT FROM last_event.photo_content_sha256::text THEN
        RAISE EXCEPTION 'inspection_evidence_changed' USING ERRCODE = 'SH002';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS field_task_inspection_close_gate ON field_tasks;
CREATE TRIGGER field_task_inspection_close_gate BEFORE UPDATE OF status ON field_tasks
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
