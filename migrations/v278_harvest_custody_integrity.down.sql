-- v278 rollback: removes the custody append-only triggers, the lot identity trigger and the
-- market listing's harvest_lot_id, and restores ON DELETE CASCADE on both v65 foreign keys.
-- Rollback script, not listed in MANIFEST.txt (forward-only manifest, as for every *.down.sql).
-- Data note: dropping market_sales_listings.harvest_lot_id discards which lot each listing named;
-- the listings themselves stay. Restoring CASCADE means deleting a field erases its lots and their
-- custody chain again. Roll back the platform and market code (revert the PR) first, so no writer
-- still sends harvest_lot_id. Measured on PG16: down, down again (idempotent), then v278 again.
BEGIN;
SET LOCAL lock_timeout = '15s';
DROP INDEX IF EXISTS idx_market_sales_listings_harvest_lot;
ALTER TABLE market_sales_listings DROP CONSTRAINT IF EXISTS market_sales_listings_harvest_lot_id_fkey;
ALTER TABLE market_sales_listings DROP COLUMN IF EXISTS harvest_lot_id;
DROP TRIGGER IF EXISTS harvest_lots_identity_immutable ON harvest_lots;
DROP FUNCTION IF EXISTS harvest_lot_identity_immutable();
ALTER TABLE custody_chain_events DROP CONSTRAINT IF EXISTS custody_chain_events_harvest_lot_id_fkey;
ALTER TABLE custody_chain_events ADD CONSTRAINT custody_chain_events_harvest_lot_id_fkey
  FOREIGN KEY (harvest_lot_id) REFERENCES harvest_lots(harvest_lot_id) ON DELETE CASCADE;
ALTER TABLE harvest_lots DROP CONSTRAINT IF EXISTS harvest_lots_field_id_fkey;
ALTER TABLE harvest_lots ADD CONSTRAINT harvest_lots_field_id_fkey
  FOREIGN KEY (field_id) REFERENCES fields(field_id) ON DELETE CASCADE;
DROP TRIGGER IF EXISTS custody_chain_events_no_truncate ON custody_chain_events;
DROP TRIGGER IF EXISTS custody_chain_events_immutable ON custody_chain_events;
DROP FUNCTION IF EXISTS custody_chain_event_immutable();
COMMIT;
