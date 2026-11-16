-- v280 rollback: removes water_ledger.irrigation_reported_by.
-- Rollback script, not listed in MANIFEST.txt (forward-only manifest, as for every *.down.sql).
-- Order: roll back the code first (revert the W0-13 change: the platform router, the water-ledger
-- worker and LEDGER_SELECT_COLS read and write this column), then run this script. Idempotent.
-- Data note: dropping the column forgets who reported each human irrigation figure. The
-- irrigation_mm values themselves stay in place; after the rollback the worker treats them as
-- its own again and overwrites today's with irrigation_runs' sum on its next poll.
BEGIN;
SET LOCAL lock_timeout='15s';
ALTER TABLE water_ledger DROP COLUMN IF EXISTS irrigation_reported_by;
COMMIT;
