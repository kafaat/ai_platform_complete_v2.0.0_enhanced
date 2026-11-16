-- v281: a ground-scouting task created from a vegetation signal anomaly, stored once per
-- request (plan item W1-20, findings remote-7 / scout-5).
-- ════════════════════════════════════════════════════════════════════════
-- The fault: vegetation-analysis-service's ground-verification bridge POSTs a scouting task for a
-- signal anomaly and requires a persisted task reference back, but no service served that route:
-- every verification request failed (424 on the manual path, verification_bridge_error on the
-- automatic one). field-management-service owns field_tasks (docs/architecture/db_ownership.yml)
-- and now serves POST/GET /internal/field-tasks/scouting. These columns carry what the task needs
-- that field_tasks did not hold:
--   * anomaly_ref           — the vegetation anomaly the task verifies (urn:sahool:anomaly:...);
--   * season_id             — the season the anomaly belongs to;
--   * geometry_ref          — where to look, when the anomaly names an area;
--   * verification_deadline — by when the ground check is due;
--   * reason_codes          — the anomaly's reason codes (signal only, never a diagnosis);
--   * scouting_idempotency_key / scouting_request_digest — the caller's Idempotency-Key and the
--     sha256 of the request it named. A replay with the same key and body returns the stored
--     task; the same key with another body is refused (409). One task per key per tenant;
--   * requested_by_service  — the authenticated service that asked (X-Service-Name).
--
-- One task per anomaly per tenant (field_tasks_scouting_anomaly_uq): a second key for an anomaly
-- that already has a task is refused, so a retried detection cannot open duplicate work.
-- Pin inspection tasks (v246) keep source_scouting_pin_id and never carry an anomaly_ref
-- (field_task_anomaly_scope_ck), so v277's close gate is unchanged for them.
--
-- Additive: nullable columns (reason_codes defaults to an empty array), partial unique indexes,
-- catalog-checked constraints. Existing rows keep their meaning. Idempotent.
-- Table owner and only writer: field-management-service.

BEGIN;

ALTER TABLE field_tasks
    ADD COLUMN IF NOT EXISTS anomaly_ref text,
    ADD COLUMN IF NOT EXISTS season_id text,
    ADD COLUMN IF NOT EXISTS geometry_ref text,
    ADD COLUMN IF NOT EXISTS verification_deadline timestamptz,
    ADD COLUMN IF NOT EXISTS reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS scouting_idempotency_key text,
    ADD COLUMN IF NOT EXISTS scouting_request_digest text,
    ADD COLUMN IF NOT EXISTS requested_by_service text;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'field_tasks'::regclass
                      AND conname = 'field_task_anomaly_scope_ck') THEN
        -- An anomaly task has a tenant, a key and its digest, and is not a pin inspection task.
        ALTER TABLE field_tasks ADD CONSTRAINT field_task_anomaly_scope_ck CHECK (
            anomaly_ref IS NULL
            OR (tenant_id IS NOT NULL
                AND source_scouting_pin_id IS NULL
                AND scouting_idempotency_key IS NOT NULL
                AND scouting_request_digest ~ '^[0-9a-f]{64}$'
                AND jsonb_typeof(reason_codes) = 'array')
        );
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS field_tasks_scouting_idempotency_uq
    ON field_tasks (tenant_id, scouting_idempotency_key)
    WHERE scouting_idempotency_key IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS field_tasks_scouting_anomaly_uq
    ON field_tasks (tenant_id, anomaly_ref)
    WHERE anomaly_ref IS NOT NULL;

CREATE INDEX IF NOT EXISTS field_tasks_scouting_field_season_idx
    ON field_tasks (tenant_id, field_id, season_id)
    WHERE anomaly_ref IS NOT NULL;

COMMENT ON COLUMN field_tasks.anomaly_ref IS
    'Vegetation signal anomaly this ground-scouting task verifies (v281, W1-20). NULL for other tasks.';
COMMENT ON COLUMN field_tasks.scouting_idempotency_key IS
    'Idempotency-Key of the request that created this anomaly task; unique per tenant (v281).';
COMMENT ON COLUMN field_tasks.scouting_request_digest IS
    'sha256 of the normalized request the key named; a replay with another body is refused (v281).';

COMMIT;
