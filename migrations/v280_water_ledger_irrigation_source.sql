-- v280: water_ledger.irrigation_source — where a day's irrigation_mm came from when it is a
-- declared source other than the row's own writer (plan item W1-13, finding water-5, manual part).
-- ════════════════════════════════════════════════════════════════════════
-- The gap: water measured in the farm operations ledger (farm_water_records.water_volume_m3, a
-- meter or a computed volume recorded with a completed operation on a field) never reached the
-- daily water ledger, so the FAO-56 balance read the day as "no irrigation recorded" and
-- recommended watering a field that had been watered.
--
-- sahool-platform now projects the day's measured farm water onto water_ledger.irrigation_mm
-- (volume m3 / area ha / 10 = mm) through the W0-13 report path: the figure is the day's applied
-- water and the water-balance worker recomputes the balance around it (irrigation_reported_by).
-- This column says the figure is that projection:
--   NULL          irrigation_mm is the row writer's own figure (worker irrigation_runs sum,
--                 a person's entry or report, an as-applied reconciliation);
--   'farm_ledger' irrigation_mm is the sum of the day's measured farm_water_records on the field.
-- Any other write of irrigation_mm clears it, so the label never outlives the figure it describes.
--
-- Additive and nullable: existing rows keep their meaning (NULL), no backfill. Idempotent.
-- Table owner and only writer: sahool-platform (docs/architecture/db_ownership.yml).

BEGIN;

ALTER TABLE water_ledger ADD COLUMN IF NOT EXISTS irrigation_source TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'water_ledger_irrigation_source_check'
          AND conrelid = 'public.water_ledger'::regclass
    ) THEN
        ALTER TABLE water_ledger ADD CONSTRAINT water_ledger_irrigation_source_check
            CHECK (irrigation_source IS NULL OR irrigation_source IN ('farm_ledger'));
    END IF;
END $$;

COMMENT ON COLUMN water_ledger.irrigation_source IS
    'Declared source of irrigation_mm (v280, W1-13). NULL: the row writer''s own figure. '
    '''farm_ledger'': the sum of the day''s measured farm_water_records on the field '
    '(volume m3 / field area ha / 10). Cleared by any other write of irrigation_mm.';

COMMIT;
