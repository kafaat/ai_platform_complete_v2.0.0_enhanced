-- v285: water_ledger.rain_source names reanalysis rain as reanalysis
-- (gap WATER-LEDGER-RAIN-SOURCE-REANALYSIS-LABEL-01).
-- ════════════════════════════════════════════════════════════════════════
-- The fault: v279 allows rain_source IN ('forecast', 'observed'), and the daily water-ledger
-- worker labels rain re-recorded from the weather-service archive 'observed'. That archive is
-- the ERA5 reanalysis (services/sahool-platform/api/water_ledger_inputs.py), a model product,
-- not a rain gauge on a station and not a measurement in the field. A reader of 'observed' could
-- take the figure for measured rain.
--
-- The CHECK now allows (same constraint name, so a re-applied v279 sees it and adds nothing):
--   forecast          the day's forecast when the row is written (unchanged);
--   reanalysis        the weather-service archive (ERA5 reanalysis), re-recorded once the archive
--                     has the day. The worker writes this value from this version on;
--   station_observed  a weather station's rain gauge (reserved: no writer yet);
--   field_measured    a gauge or measurement in the field itself (reserved: no writer yet);
--   observed          legacy v279 value, kept only so rows this migration cannot prove to be
--                     archive rain stay valid. No code writes it any more.
--
-- Relabelling existing rows, and why it is proven: from v279 on, exactly one code path writes
-- the literal 'observed', the worker's archive reconciliation (phase_runtime_workers, the
-- conditional UPDATE ... WHERE created_by = 'water-balance-auto'), and it always writes rain_mm
-- with it. Every other writer of water_ledger either clears rain_source when it writes rain_mm
-- (water_ledger_compute) or does not touch rain_mm (the as-applied and farm-ledger paths). So a
-- row that still holds rain_source = 'observed', created_by = 'water-balance-auto' and a
-- rain_mm holds the archive figure the worker wrote, and becomes 'reanalysis'. A row that holds
-- 'observed' without those facts (a hand-written row, a row whose owner changed) is left as
-- 'observed': its origin is not proven, and the migration reports how many such rows it left.
--
-- Fail loudly, never silently: water_ledger has ENABLE + FORCE ROW LEVEL SECURITY (v98), so a
-- role subject to RLS (not superuser, not BYPASSRLS, the owner included under FORCE) would see no
-- row and relabel none while this comment claims the relabel. Such a role is refused.
--
-- Deploy order: apply v285 before the platform code that writes 'reanalysis'. Until then the
-- old CHECK refuses the new value and the worker skips that field's day with the constraint
-- named in its log (a declared skip, no wrong row).
--
-- Idempotent: the CHECK is replaced only when it does not already allow 'reanalysis', and a
-- second relabel finds no row. Owner and only writer: sahool-platform
-- (docs/architecture/db_ownership.yml). Rollback: v285_water_ledger_rain_source_reanalysis.down.sql.

BEGIN;
SET LOCAL lock_timeout = '15s';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles
         WHERE rolname = current_user AND (rolsuper OR rolbypassrls)
    ) AND EXISTS (
        SELECT 1 FROM pg_class
         WHERE oid = 'water_ledger'::regclass AND relrowsecurity
    ) THEN
        RAISE EXCEPTION
            'v285: role % is subject to RLS on water_ledger and cannot see the rows to relabel; '
            'apply as the superuser/BYPASSRLS migration owner', current_user;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'water_ledger'::regclass
           AND conname = 'water_ledger_rain_source_check'
           AND pg_get_constraintdef(oid) LIKE '%reanalysis%'
    ) THEN
        ALTER TABLE water_ledger DROP CONSTRAINT IF EXISTS water_ledger_rain_source_check;
        ALTER TABLE water_ledger ADD CONSTRAINT water_ledger_rain_source_check
            CHECK (rain_source IS NULL OR rain_source IN (
                'forecast', 'reanalysis', 'station_observed', 'field_measured', 'observed'));
    END IF;
END
$$;

DO $$
DECLARE
    relabelled bigint;
    left_legacy bigint;
BEGIN
    UPDATE water_ledger
       SET rain_source = 'reanalysis'
     WHERE rain_source = 'observed'
       AND created_by = 'water-balance-auto'
       AND rain_mm IS NOT NULL;
    GET DIAGNOSTICS relabelled = ROW_COUNT;
    SELECT count(*) INTO left_legacy FROM water_ledger WHERE rain_source = 'observed';
    RAISE NOTICE 'v285: % archive rain row(s) relabelled reanalysis; % legacy observed row(s) '
                 'left (archive origin not proven)', relabelled, left_legacy;
END
$$;

COMMENT ON COLUMN water_ledger.rain_source IS
    'v279/v285: forecast (the day''s forecast when the row is written) | reanalysis (the '
    'weather-service archive, ERA5 reanalysis, re-recorded once it has the day) | '
    'station_observed (a station rain gauge) | field_measured (measured in the field) | '
    'observed (legacy v279 value whose archive origin v285 could not prove; no longer written).';

COMMIT;
