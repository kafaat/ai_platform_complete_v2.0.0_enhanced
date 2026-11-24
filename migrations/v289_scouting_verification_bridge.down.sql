-- Refuse to discard recorded visits/assessments or uncertain deliveries.
BEGIN;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM scouting_verification_links)
       OR EXISTS (SELECT 1 FROM scouting_verification_outbox) THEN
        RAISE EXCEPTION 'verification_bridge_down_requires_empty_tables';
    END IF;
END $$;
DROP TABLE scouting_verification_outbox;
DROP TABLE scouting_verification_assessments;
DROP TABLE scouting_verification_versions, scouting_verification_links;
DROP FUNCTION scouting_verification_delivery_insert_guard();
DROP FUNCTION scouting_verification_delivery_guard();
DROP FUNCTION scouting_verification_assessment_guard();
DROP FUNCTION scouting_verification_link_guard();
COMMIT;
