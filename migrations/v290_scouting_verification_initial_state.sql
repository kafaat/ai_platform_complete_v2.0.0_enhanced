-- v290: every verification delivery starts before its first claim.
-- v289 already binds the body to the reviewed assessment and guards UPDATEs.
-- Keep its applied bytes and existing rows unchanged; this independent trigger
-- closes the initial INSERT path, including SQL issued outside the dispatcher.
BEGIN;
SET LOCAL lock_timeout = '15s';

CREATE OR REPLACE FUNCTION public.scouting_verification_delivery_initial_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF NEW.state IS DISTINCT FROM 'pending'
       OR NEW.attempts IS DISTINCT FROM 0
       OR NEW.lease_token IS NOT NULL
       OR NEW.lease_until IS NOT NULL
       OR NEW.receipt IS NOT NULL
       OR NEW.last_error IS NOT NULL THEN
        RAISE EXCEPTION 'verification_delivery_initial_state_invalid' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS scouting_verification_delivery_initial_guard
    ON public.scouting_verification_outbox;
CREATE TRIGGER scouting_verification_delivery_initial_guard
    BEFORE INSERT ON public.scouting_verification_outbox
    FOR EACH ROW EXECUTE FUNCTION public.scouting_verification_delivery_initial_guard();

COMMENT ON FUNCTION public.scouting_verification_delivery_initial_guard() IS
    'New deliveries start pending with zero attempts and no lease, receipt or error. Existing rows and v289 update/content guards are unchanged.';

COMMIT;
