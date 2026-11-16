-- SAHOOL v278 — migrations/v278_harvest_custody_integrity.sql
-- Harvest custody integrity and the market link (owner decisions 2 and 3, 2026-11-15).
--
-- What was wrong (v65 + v9_market, verified on main dec6dae4):
-- ① custody_chain_events was described as append-only but nothing enforced it: any writer with
--   table rights could UPDATE or DELETE an event (content_hash is computed by the application and
--   would simply be rewritten with it).
-- ② Deleting a field deleted its harvest lots, and deleting a lot deleted its custody chain
--   (both ON DELETE CASCADE): the platform's DELETE /api/v1/fields/{id}, merge and split erased
--   the traceability record of everything harvested there.
-- ③ A lot's quantity, field, tenant and harvest date could be changed after custody events were
--   recorded against them, so the remaining-quantity check had a moving base.
-- ④ market_sales_listings.batch_id is UUID and is checked against inventory_batches, whose ids are
--   'bat_…' text: no listing could ever name a batch, and nothing tied a listed quantity to a
--   harvest lot.
--
-- This migration:
-- ① BEFORE UPDATE OR DELETE (row) and BEFORE TRUNCATE (statement) triggers on custody_chain_events.
-- ② Both foreign keys become ON DELETE RESTRICT. The platform answers 409 before deleting, merging
--   or splitting a field that has harvest lots (api/routers/fields.py).
-- ③ BEFORE UPDATE trigger on harvest_lots: harvest_lot_id, tenant_id, field_id, quantity_kg and
--   harvest_date are immutable; status, grade, moisture, crop, season and notes stay writable.
-- ④ market_sales_listings.harvest_lot_id (text, FK harvest_lots ON DELETE RESTRICT). The legacy
--   UUID batch_id column is left as it is. The market MCP server checks a listed quantity against
--   the lot under the lot's row lock (services/mcp_servers/market_server.py).
--
-- A maintenance correction is still possible for the schema owner (ALTER TABLE … DISABLE TRIGGER
-- inside a reviewed transaction); the application roles cannot do it. Idempotent; RLS unchanged.

BEGIN;
SET LOCAL lock_timeout = '15s';

-- ① custody events are append-only.
CREATE OR REPLACE FUNCTION custody_chain_event_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
  RAISE EXCEPTION 'custody_chain_event_immutable' USING ERRCODE = '55000';
END; $$;
DROP TRIGGER IF EXISTS custody_chain_events_immutable ON custody_chain_events;
CREATE TRIGGER custody_chain_events_immutable BEFORE UPDATE OR DELETE ON custody_chain_events
  FOR EACH ROW EXECUTE FUNCTION custody_chain_event_immutable();
DROP TRIGGER IF EXISTS custody_chain_events_no_truncate ON custody_chain_events;
CREATE TRIGGER custody_chain_events_no_truncate BEFORE TRUNCATE ON custody_chain_events
  FOR EACH STATEMENT EXECUTE FUNCTION custody_chain_event_immutable();

-- ② no cascading erasure of the chain.
ALTER TABLE harvest_lots DROP CONSTRAINT IF EXISTS harvest_lots_field_id_fkey;
ALTER TABLE harvest_lots ADD CONSTRAINT harvest_lots_field_id_fkey
  FOREIGN KEY (field_id) REFERENCES fields(field_id) ON DELETE RESTRICT;
ALTER TABLE custody_chain_events DROP CONSTRAINT IF EXISTS custody_chain_events_harvest_lot_id_fkey;
ALTER TABLE custody_chain_events ADD CONSTRAINT custody_chain_events_harvest_lot_id_fkey
  FOREIGN KEY (harvest_lot_id) REFERENCES harvest_lots(harvest_lot_id) ON DELETE RESTRICT;

-- ③ a lot's identity and quantity do not move under its custody chain.
CREATE OR REPLACE FUNCTION harvest_lot_identity_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
  IF NEW.harvest_lot_id IS DISTINCT FROM OLD.harvest_lot_id
     OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
     OR NEW.field_id IS DISTINCT FROM OLD.field_id
     OR NEW.quantity_kg IS DISTINCT FROM OLD.quantity_kg
     OR NEW.harvest_date IS DISTINCT FROM OLD.harvest_date THEN
    RAISE EXCEPTION 'harvest_lot_identity_immutable' USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END; $$;
DROP TRIGGER IF EXISTS harvest_lots_identity_immutable ON harvest_lots;
CREATE TRIGGER harvest_lots_identity_immutable BEFORE UPDATE ON harvest_lots
  FOR EACH ROW EXECUTE FUNCTION harvest_lot_identity_immutable();

-- ④ a sales listing can name the harvest lot it sells from.
ALTER TABLE market_sales_listings ADD COLUMN IF NOT EXISTS harvest_lot_id VARCHAR(50);
ALTER TABLE market_sales_listings DROP CONSTRAINT IF EXISTS market_sales_listings_harvest_lot_id_fkey;
ALTER TABLE market_sales_listings ADD CONSTRAINT market_sales_listings_harvest_lot_id_fkey
  FOREIGN KEY (harvest_lot_id) REFERENCES harvest_lots(harvest_lot_id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS idx_market_sales_listings_harvest_lot
  ON market_sales_listings (harvest_lot_id) WHERE harvest_lot_id IS NOT NULL;

COMMENT ON TRIGGER custody_chain_events_immutable ON custody_chain_events IS
  'custody events are append-only (v278)';
COMMENT ON COLUMN market_sales_listings.harvest_lot_id IS
  'harvest lot this listing sells from; listed quantity checked against the lot remainder (v278)';
COMMIT;
