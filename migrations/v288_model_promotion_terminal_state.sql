-- v288: a model promotion leaves the worker queue, and a serving alias never defaults to active
-- (finding F-D04; gap A-QUEUE-WITH-NO-TERMINAL-STATE-REPUBLISHES-FOREVER-01).
-- ════════════════════════════════════════════════════════════════════════
-- The faults, measured on PostgreSQL (tests_v9/test_model_promotion_ack_live_pg.py):
--   1. model_promotion_history_runtime (v108) has no state column. The model worker claimed
--      decision = 'promote' rows, released the claim without changing anything, and claimed the
--      same row again on the next cycle: in the default deployed configuration
--      (MODEL_SERVING_ENABLED unset) a blocked promotion was re-picked every cycle, and with
--      serving enabled the same promotion was requested again every cycle.
--   2. model_serving_aliases_runtime.status defaults to 'active' (v108), and the platform
--      writer omitted the column, so a promote decision wrote the alias 'active' with no
--      acknowledgement from any serving backend.
--
-- What this adds:
--   model_promotion_history_runtime.status         pending (default) -> requested | blocked |
--                                                  skipped. The worker claims only 'pending'
--                                                  rows and writes one terminal value with the
--                                                  claim release, so a processed row is never
--                                                  claimed again.
--     requested  the promotion was requested from the serving backend; the alias waits as
--                pending_external_ack until an acknowledgement path records it.
--     blocked    serving disabled, backend URL or artifact metadata missing, or no target model.
--                Terminal: enabling serving later does not replay old promotions; a new
--                promotion decision is needed.
--     skipped    the decision was not 'promote'.
--   model_promotion_history_runtime.status_reason  the worker's reason for blocked/skipped
--                                                  (e.g. model_serving_disabled), NULL otherwise.
--   model_serving_aliases_runtime.status DEFAULT 'pending_external_ack' instead of 'active', so
--   an insert that names no status can not make an alias serve.
--
-- Existing rows, so the first worker cycle after this migration does not replay history:
--   decision <> 'promote'                                   -> skipped (decision_<decision>);
--   decision = 'promote' whose promotion is already the alias's pending_external_ack request
--   (written only by the worker's request branch)           -> requested;
--   every other promote row stays pending and is processed once more under the new rules.
-- Alias rows that already hold 'active' are not changed: no acknowledgement path exists, so
-- each such row was written without one, but which of them actually serve is an operator
-- fact this migration can not prove. It reports their number (NOTICE) for the owner to decide.
--
-- Fail loudly, never silently: both tables have ENABLE + FORCE ROW LEVEL SECURITY (v108), so a
-- role subject to RLS would see no row and backfill none. Such a role is refused.
--
-- Deploy order: apply v288 before the platform code that claims status = 'pending'; until then
-- the worker's claim fails on the missing column and processes nothing (no wrong row).
--
-- Idempotent: ADD COLUMN IF NOT EXISTS, a CHECK added only when absent, and a backfill that
-- touches only 'pending' rows. Writers: sahool-platform (phase_runtime_store,
-- phase_runtime_workers); declared owner agriai-engine (docs/architecture/db_ownership.yml).
-- Rollback: v288_model_promotion_terminal_state.down.sql.

BEGIN;
SET LOCAL lock_timeout = '15s';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles
         WHERE rolname = current_user AND (rolsuper OR rolbypassrls)
    ) THEN
        RAISE EXCEPTION
            'v288: role % is subject to RLS on model_promotion_history_runtime and cannot see the '
            'rows to backfill; apply as the superuser/BYPASSRLS migration owner', current_user;
    END IF;
END
$$;

ALTER TABLE model_promotion_history_runtime
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS status_reason TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'model_promotion_history_runtime'::regclass
           AND conname = 'model_promotion_history_runtime_status_check'
    ) THEN
        ALTER TABLE model_promotion_history_runtime
            ADD CONSTRAINT model_promotion_history_runtime_status_check
            CHECK (status IN ('pending', 'requested', 'blocked', 'skipped'));
    END IF;
END
$$;

UPDATE model_promotion_history_runtime
   SET status = 'skipped', status_reason = 'decision_' || decision
 WHERE status = 'pending' AND decision <> 'promote';

UPDATE model_promotion_history_runtime p
   SET status = 'requested'
  FROM model_serving_aliases_runtime a
 WHERE p.status = 'pending' AND p.decision = 'promote'
   AND a.tenant_id = p.tenant_id AND a.alias = p.alias
   AND a.promotion_id = p.promotion_id AND a.status = 'pending_external_ack';

CREATE INDEX IF NOT EXISTS idx_model_promotion_runtime_pending
    ON model_promotion_history_runtime (created_at) WHERE status = 'pending';

ALTER TABLE model_serving_aliases_runtime ALTER COLUMN status SET DEFAULT 'pending_external_ack';

COMMENT ON COLUMN model_promotion_history_runtime.status IS
    'v288: pending (queued for the model worker) | requested (asked of the serving backend; the alias waits as pending_external_ack) | blocked | skipped. Terminal once not pending.';
COMMENT ON COLUMN model_serving_aliases_runtime.status IS
    'v288: pending_external_ack until an acknowledgement path records the serving backend''s ack; no writer sets active without one.';

DO $$
DECLARE
    unacked bigint;
BEGIN
    SELECT count(*) INTO unacked FROM model_serving_aliases_runtime WHERE status = 'active';
    IF unacked > 0 THEN
        RAISE NOTICE
            'v288: % model_serving_aliases_runtime row(s) hold active, written before v288 '
            'without an acknowledgement; left unchanged for the owner to decide', unacked;
    END IF;
END
$$;

COMMIT;
