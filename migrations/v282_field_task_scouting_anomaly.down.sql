-- v282 rollback: removes the anomaly scouting-task columns, indexes and constraint on field_tasks.
-- Rollback script, not listed in MANIFEST.txt (forward-only manifest, as for every *.down.sql).
-- Order: roll back the code first (revert the W1-20 change: field-management-service's
-- fm_scouting_tasks.py routes and the vegetation / workspace callers read and write these
-- columns), then run this script. Idempotent.
-- Data note: the anomaly tasks themselves stay in field_tasks as ordinary 'scouting' tasks, but
-- which anomaly each verifies, its season, deadline, reason codes and idempotency key are lost;
-- vegetation anomalies keep their task_ref (urn:sahool:task:<task_id>) pointing at those rows.
BEGIN;
SET LOCAL lock_timeout='15s';
DROP INDEX IF EXISTS field_tasks_scouting_field_season_idx;
DROP INDEX IF EXISTS field_tasks_scouting_anomaly_uq;
DROP INDEX IF EXISTS field_tasks_scouting_idempotency_uq;
ALTER TABLE field_tasks DROP CONSTRAINT IF EXISTS field_task_anomaly_scope_ck;
ALTER TABLE field_tasks
    DROP COLUMN IF EXISTS requested_by_service,
    DROP COLUMN IF EXISTS scouting_request_digest,
    DROP COLUMN IF EXISTS scouting_idempotency_key,
    DROP COLUMN IF EXISTS reason_codes,
    DROP COLUMN IF EXISTS verification_deadline,
    DROP COLUMN IF EXISTS geometry_ref,
    DROP COLUMN IF EXISTS season_id,
    DROP COLUMN IF EXISTS anomaly_ref;
COMMIT;
