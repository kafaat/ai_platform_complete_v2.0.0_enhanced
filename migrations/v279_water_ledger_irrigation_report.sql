-- v279: water_ledger.irrigation_reported_by — a person's applied-water report on a day whose
-- balance the water-balance worker computes (plan item W0-13, finding mobile-3).
-- ════════════════════════════════════════════════════════════════════════
-- The fault: POST /api/v1/fields/{id}/water-ledger was a full upsert. The mobile app logs the
-- water a farmer applied; replayed from the offline outbox it sent {ledger_date, irrigation_mm}
-- and the upsert wrote NULL over et0_mm, depletion_mm, deficit_mm and confidence that the
-- worker had computed for that day. And because a human write did not change created_by on an
-- existing worker row, the worker (polling every few seconds) then wrote irrigation_runs' sum
-- over the farmer's number. Either the balance or the farmer's water was lost.
--
-- This column records who reported irrigation_mm when the row's balance belongs to the worker.
-- NULL: irrigation_mm came from the worker (irrigation_runs) or from the author of a full manual
-- entry. NOT NULL: the worker keeps irrigation_mm as reported and recomputes the balance around
-- it, instead of overwriting it or skipping the day.
--
-- Additive and nullable: existing rows keep their meaning (NULL), no backfill. Idempotent.
-- Table owner and only writer: sahool-platform (docs/architecture/db_ownership.yml).

BEGIN;

ALTER TABLE water_ledger ADD COLUMN IF NOT EXISTS irrigation_reported_by TEXT;

COMMENT ON COLUMN water_ledger.irrigation_reported_by IS
    'Who reported irrigation_mm for a day whose balance the water-balance worker computes (v279). '
    'NULL: irrigation_mm is the worker''s (irrigation_runs) or the full manual entry author''s. '
    'NOT NULL: the worker keeps the reported irrigation_mm and recomputes the balance around it.';

COMMIT;
