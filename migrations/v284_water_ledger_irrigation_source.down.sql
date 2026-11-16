-- v284 rollback: removes water_ledger.irrigation_source and its CHECK.
-- Rollback script, not listed in MANIFEST.txt (forward-only manifest, as for every *.down.sql).
-- Order: roll back the code first (revert W1-13: the farm-ledger projection and the water-ledger
-- writers read and write this column), then run this script. Idempotent.
-- Data note: dropping the column forgets which irrigation figures were projected from the farm
-- ledger. The irrigation_mm values and their reporter stay in place.
BEGIN;
SET LOCAL lock_timeout='15s';
ALTER TABLE water_ledger DROP CONSTRAINT IF EXISTS water_ledger_irrigation_source_check;
ALTER TABLE water_ledger DROP COLUMN IF EXISTS irrigation_source;
COMMIT;
