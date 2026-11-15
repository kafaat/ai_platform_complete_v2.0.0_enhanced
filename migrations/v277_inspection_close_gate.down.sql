-- v277 rollback: removes the pin-inspection close gate and the reopen trigger on field_tasks.
-- Rollback script, not listed in MANIFEST.txt (forward-only manifest, as for every *.down.sql).
-- Order: roll back the code first (revert the PR that added v274-v277), then run the down
-- scripts newest first: v277, v276, v275, v274. Each is idempotent.
-- Re-applying the forward migration afterwards recreates the objects WITHOUT the role grants:
-- run migrations/bootstrap_postgres.sh (or apply_in_compose.sh) again, which also repeats
-- v276's REVOKEs after its blanket GRANT.
-- Data note: no table and no row is removed; field_tasks keeps its rows, and any reopen
-- events already written stay in inspection_handoffs until v275 is rolled back.
BEGIN;
SET LOCAL lock_timeout='15s';
DROP TRIGGER IF EXISTS field_task_inspection_reopen ON field_tasks;
DROP TRIGGER IF EXISTS field_task_inspection_close_gate ON field_tasks;
DROP FUNCTION IF EXISTS field_task_inspection_reopen();
DROP FUNCTION IF EXISTS field_task_inspection_close_gate();
COMMIT;
