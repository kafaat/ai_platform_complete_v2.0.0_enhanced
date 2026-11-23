-- v288 rollback: drop the promotion queue state and restore the v108 alias default.
-- Rollback script, not listed in MANIFEST.txt (forward-only manifest, as for every *.down.sql).
--
-- Roll back the platform code first (phase_runtime_workers claims status = 'pending' and writes
-- status/status_reason), so no worker still reads or writes the columns once they are gone.
--
-- What is lost, and what that means: the terminal state of every processed promotion. The
-- pre-v288 worker claims every decision = 'promote' row again on each cycle, so after this
-- rollback each promote row is re-picked forever (blocked rows re-blocked; with serving enabled,
-- requested again) - the fault v288 fixed. The alias default returns to 'active', but the
-- platform writer keeps naming pending_external_ack explicitly, so no alias becomes active by
-- default unless that code is rolled back too.
-- Idempotent: every statement is IF EXISTS or a plain SET DEFAULT.

BEGIN;
SET LOCAL lock_timeout = '15s';

DROP INDEX IF EXISTS idx_model_promotion_runtime_pending;
ALTER TABLE model_promotion_history_runtime
    DROP CONSTRAINT IF EXISTS model_promotion_history_runtime_status_check;
ALTER TABLE model_promotion_history_runtime
    DROP COLUMN IF EXISTS status_reason,
    DROP COLUMN IF EXISTS status;
ALTER TABLE model_serving_aliases_runtime ALTER COLUMN status SET DEFAULT 'active';
COMMENT ON COLUMN model_serving_aliases_runtime.status IS NULL;

COMMIT;
