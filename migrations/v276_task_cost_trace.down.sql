-- v276 rollback: removes the task cost trace (task_expense_links, task_cost_history) and the
-- record_field_task_cost trigger on field_tasks.
-- Rollback script, not listed in MANIFEST.txt (forward-only manifest, as for every *.down.sql).
-- Order: roll back the code first (revert the PR that added v274-v277), then run the down
-- scripts newest first: v277, v276, v275, v274. Each is idempotent.
-- Re-applying the forward migration afterwards recreates the objects WITHOUT the role grants:
-- run migrations/bootstrap_postgres.sh (or apply_in_compose.sh) again, which also repeats
-- v276's REVOKEs after its blanket GRANT.
-- Data note: dropping the tables discards the expense links and the cost history.
-- field_tasks.actual_cost_usd itself is untouched.
BEGIN;
SET LOCAL lock_timeout='15s';
DROP TRIGGER IF EXISTS record_field_task_cost ON field_tasks;
DROP FUNCTION IF EXISTS record_field_task_cost();
DROP TABLE IF EXISTS task_cost_history;
DROP TABLE IF EXISTS task_expense_links;
DROP FUNCTION IF EXISTS task_cost_history_guard();
DROP FUNCTION IF EXISTS task_expense_link_guard();
COMMIT;
