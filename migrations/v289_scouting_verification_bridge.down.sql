-- Refuse to discard recorded visits/assessments or uncertain deliveries.
BEGIN;
-- Run as the migration owner (superuser/BYPASSRLS). row_security=off makes a session that
-- RLS would blind fail loudly instead of seeing "no rows" and dropping recorded data.
SET LOCAL row_security = off;
DO $$ BEGIN
    IF to_regclass('scouting_verification_links') IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM scouting_verification_links) THEN
            RAISE EXCEPTION 'verification_bridge_down_requires_empty_tables';
        END IF;
    END IF;
    IF to_regclass('scouting_verification_outbox') IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM scouting_verification_outbox) THEN
            RAISE EXCEPTION 'verification_bridge_down_requires_empty_tables';
        END IF;
    END IF;
END $$;
DROP TABLE IF EXISTS scouting_verification_outbox;
DROP TABLE IF EXISTS scouting_verification_assessments;
DROP TABLE IF EXISTS scouting_verification_versions, scouting_verification_links;
DROP FUNCTION IF EXISTS scouting_verification_delivery_insert_guard();
DROP FUNCTION IF EXISTS scouting_verification_delivery_guard();
DROP FUNCTION IF EXISTS scouting_verification_assessment_guard();
DROP FUNCTION IF EXISTS scouting_verification_link_guard();
COMMIT;
