-- v290 rollback: remove only the initial-state guard added by v290.
-- No rows, receipts or v289 guards are changed. This deliberately restores the
-- weaker pre-v290 INSERT contract; future INSERTs lose this initial-state guarantee.
BEGIN;
SET LOCAL lock_timeout = '15s';

DO $$ BEGIN
    IF to_regclass('public.scouting_verification_outbox') IS NOT NULL THEN
        DROP TRIGGER IF EXISTS scouting_verification_delivery_initial_guard
            ON public.scouting_verification_outbox;
    END IF;
END $$;
DROP FUNCTION IF EXISTS public.scouting_verification_delivery_initial_guard();

COMMIT;
