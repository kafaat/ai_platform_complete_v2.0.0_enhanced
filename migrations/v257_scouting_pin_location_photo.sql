-- v257: scouting pins keep where their position came from.
-- ════════════════════════════════════════════════════════════════════════
-- Priority 4 (owner): the app knew whether a pin was a GPS fix or the field centre but sent
-- only coordinates, so a supervisor on another device could not tell a measured pin from a
-- field-centre one. location_source and accuracy_m now travel with the pin.
--   * location_source: gps | manual | field_centroid | unknown. Rows written before this
--     migration (and by older app versions that do not send it) are 'unknown' (the column
--     default fills existing rows when it is added). Nothing is inferred from coordinates.
--   * accuracy_m: the device-reported radius in metres. Only a GPS fix has one; the CHECK
--     refuses an accuracy on a manual, field-centre or unknown position.
--
-- The observation photo is NOT linked here. Owner decision (2026-11-13): its single source of
-- truth is scout_photo_evidence (v260_scout_photo_evidence, owned by scout-ingest), bound to
-- (tenant_id, field_id, pin_id). An earlier draft of this unmerged migration added
-- scouting_pins.photo_document_id (FK to documents); it was removed before merge so that there
-- is one photo link, not two. The file name keeps "photo" only because it is already registered.
--
-- Additive and idempotent on a re-applied MANIFEST: ADD COLUMN IF NOT EXISTS and
-- catalog-checked constraints. scouting_pins keeps its FORCE RLS and tenant policy (v94/v192).
ALTER TABLE scouting_pins ADD COLUMN IF NOT EXISTS location_source TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE scouting_pins ADD COLUMN IF NOT EXISTS accuracy_m DOUBLE PRECISION;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'scouting_pins_location_source_ck'
          AND conrelid = 'scouting_pins'::regclass
    ) THEN
        ALTER TABLE scouting_pins ADD CONSTRAINT scouting_pins_location_source_ck
            CHECK (location_source IN ('gps', 'manual', 'field_centroid', 'unknown'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'scouting_pins_accuracy_ck'
          AND conrelid = 'scouting_pins'::regclass
    ) THEN
        ALTER TABLE scouting_pins ADD CONSTRAINT scouting_pins_accuracy_ck
            CHECK (accuracy_m IS NULL OR (location_source = 'gps' AND accuracy_m >= 0));
    END IF;
END $$;

COMMENT ON COLUMN scouting_pins.location_source IS
    'gps | manual | field_centroid | unknown (rows before v257 and clients that do not send it).';
COMMENT ON COLUMN scouting_pins.accuracy_m IS
    'Device-reported GPS accuracy radius in metres; NULL unless location_source = gps.';
