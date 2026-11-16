-- SAHOOL v286 down — removes the canonical observations store and the raster delivery outbox.
-- Destroys the stored observations: canonical_observations is append-only by design, so this is
-- the only way rows leave it. indicators-service falls back to its declared computed path.
BEGIN;
SET LOCAL lock_timeout = '15s';
DROP TABLE IF EXISTS raster_observation_outbox;
DROP TABLE IF EXISTS canonical_observations;
DROP FUNCTION IF EXISTS canonical_observation_immutable();
COMMIT;
