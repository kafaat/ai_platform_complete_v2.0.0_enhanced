-- v274 rollback: removes the inspection evidence versions (gap P3) and the shared append-only
-- trigger function field_mgmt_append_only.
-- Rollback script, not listed in MANIFEST.txt (forward-only manifest, as for every *.down.sql).
-- Order: roll back the code first (revert the PR that added v274-v277), then run the down
-- scripts newest first: v277, v276, v275, v274. Each is idempotent.
-- Re-applying the forward migration afterwards recreates the objects WITHOUT the role grants:
-- run migrations/bootstrap_postgres.sh (or apply_in_compose.sh) again, which also repeats
-- v276's REVOKEs after its blanket GRANT.
-- Run it last: field_mgmt_append_only is also used by v275's and v276's tables, so it is
-- dropped only here (plain DROP FUNCTION: it fails, changing nothing, if one still uses it).
-- Data note: dropping the table discards the evidence versions; the scout photo evidence
-- records they named are in another service's tables and stay.
BEGIN;
SET LOCAL lock_timeout='15s';
DROP TABLE IF EXISTS inspection_evidence_versions;
DROP FUNCTION IF EXISTS inspection_evidence_version_guard();
DROP FUNCTION IF EXISTS field_mgmt_append_only();
COMMIT;
