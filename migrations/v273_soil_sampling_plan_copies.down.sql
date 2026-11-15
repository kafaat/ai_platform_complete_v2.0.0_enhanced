-- v273 rollback: removes soil-service's stored copies of AI soil-sampling plans and the
-- field-cover check function (gap P6).
-- Rollback script, not listed in MANIFEST.txt (forward-only manifest, as for every *.down.sql).
-- Data note: dropping the table discards the stored plan copies. Lab samples that already
-- recorded a plan origin keep the origin values they stored; only the copy that resolved
-- them is lost. Roll back the soil-service and platform code (revert the P6 PR) first, so no
-- writer or resolver still expects the table.
-- Re-applying v273 after this rollback recreates the table WITHOUT the role grants: run
-- migrations/bootstrap_postgres.sh (or apply_in_compose.sh) again so its grants for the
-- service roles are restored. Measured on PG16: down, down again (idempotent), then v273
-- recreates the table, policy, trigger and function with RLS forced.
BEGIN;
SET LOCAL lock_timeout='15s';
DROP TRIGGER IF EXISTS soil_sampling_plan_copies_immutable ON soil_sampling_plan_copies;
DROP TABLE IF EXISTS soil_sampling_plan_copies;
DROP FUNCTION IF EXISTS soil_sampling_plan_copy_immutable();
DROP FUNCTION IF EXISTS sahool_field_covers_points(text, text, jsonb, double precision);
COMMIT;
