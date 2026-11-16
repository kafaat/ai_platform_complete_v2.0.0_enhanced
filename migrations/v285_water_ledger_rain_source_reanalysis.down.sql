-- v285 rollback: water_ledger.rain_source back to the v279 CHECK ('forecast', 'observed').
-- Rollback script, not listed in MANIFEST.txt (forward-only manifest, as for every *.down.sql).
--
-- Roll back the platform code first (water_ledger_inputs.RAIN_SOURCE_REANALYSIS), so no writer
-- still writes 'reanalysis' once the old CHECK is back.
--
-- What happens to rows that hold the new values, chosen per value and never silent:
--   reanalysis                         mapped back to 'observed'. Under v279 'observed' meant
--                                      exactly this (the archive figure the worker re-recorded),
--                                      so the mapping restores v279's own label for the same
--                                      fact; it loses only the new, more precise name.
--   station_observed, field_measured   no v279 value says "a gauge"; folding them into
--                                      'observed' would recreate the ambiguity v285 removed.
--                                      The rollback refuses (RAISE) while any such row exists and
--                                      changes nothing: decide what those rows become first.
-- Like v285 it refuses a role subject to RLS (FORCE RLS would hide the rows to check and map).
-- Idempotent: a second run maps nothing and finds the v279 CHECK already in place.

BEGIN;
SET LOCAL lock_timeout = '15s';

DO $$
DECLARE
    unmappable bigint;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles
         WHERE rolname = current_user AND (rolsuper OR rolbypassrls)
    ) AND EXISTS (
        SELECT 1 FROM pg_class
         WHERE oid = 'water_ledger'::regclass AND relrowsecurity
    ) THEN
        RAISE EXCEPTION
            'v285 rollback: role % is subject to RLS on water_ledger and cannot see the rows to '
            'check; apply as the superuser/BYPASSRLS migration owner', current_user;
    END IF;
    SELECT count(*) INTO unmappable FROM water_ledger
     WHERE rain_source IN ('station_observed', 'field_measured');
    IF unmappable > 0 THEN
        RAISE EXCEPTION
            'v285 rollback refused: % water_ledger row(s) hold station_observed/field_measured, '
            'which the v279 CHECK has no value for; nothing was changed', unmappable;
    END IF;
END
$$;

UPDATE water_ledger SET rain_source = 'observed' WHERE rain_source = 'reanalysis';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'water_ledger'::regclass
           AND conname = 'water_ledger_rain_source_check'
           AND pg_get_constraintdef(oid) NOT LIKE '%reanalysis%'
    ) THEN
        ALTER TABLE water_ledger DROP CONSTRAINT IF EXISTS water_ledger_rain_source_check;
        ALTER TABLE water_ledger ADD CONSTRAINT water_ledger_rain_source_check
            CHECK (rain_source IS NULL OR rain_source IN ('forecast', 'observed'));
    END IF;
END
$$;

COMMENT ON COLUMN water_ledger.rain_source IS
    'v279: forecast (written from the day''s forecast) | observed (re-recorded from the weather archive once it has the day).';

COMMIT;
