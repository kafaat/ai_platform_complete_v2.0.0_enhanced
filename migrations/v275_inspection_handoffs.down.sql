-- v275 rollback: removes the inspection hand-off log.
-- Rollback script, not listed in MANIFEST.txt (forward-only manifest, as for every *.down.sql).
-- Order: roll back the code first (revert the PR that added v274-v277), then run the down
-- scripts newest first: v277, v276, v275, v274. Each is idempotent.
-- Re-applying the forward migration afterwards recreates the objects WITHOUT the role grants:
-- run migrations/bootstrap_postgres.sh (or apply_in_compose.sh) again, which also repeats
-- v276's REVOKEs after its blanket GRANT.
-- Data note: dropping the table discards the hand-off and reopen history.
BEGIN;
SET LOCAL lock_timeout='15s';
DROP TABLE IF EXISTS inspection_handoffs;
DROP FUNCTION IF EXISTS inspection_handoff_revision_guard();
DROP FUNCTION IF EXISTS inspection_handoff_chain_guard();
COMMIT;
