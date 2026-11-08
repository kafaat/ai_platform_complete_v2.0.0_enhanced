-- v238_actuator_delivery_state.sql — explicit delivery state for actuator commands.
--
-- device_commands_log.status said 'sent' once the broker accepted a QoS 1 publish. That is a
-- broker acknowledgement, not a device one: nothing recorded whether the valve's firmware
-- received and applied the command. This migration adds a per-command correlation id and an
-- explicit delivery state machine, mirrored from services/actuator-service/command_delivery.py:
--
--   queued -> published | simulated | publish_failed | expired
--   published -> device_acked | device_rejected | expired
--
-- device_acked/device_rejected are only reachable from 'published' (the service moves there
-- only on a signed device ack naming the command id); a BEFORE trigger refuses any other edge
-- and refuses inserting a device/expired state directly. Legacy rows keep delivery_state NULL
-- ('untracked'). Columns only: the table keeps its existing FORCE RLS tenant_isolation policy,
-- asserted below. Additive, nullable, transactional and idempotent (IF NOT EXISTS / guarded DO).
-- Inserted before v206 so v206 stays the last MANIFEST entry.

BEGIN;
SET LOCAL lock_timeout = '15s';

DO $$
BEGIN
    IF to_regclass('public.device_commands_log') IS NULL THEN
        RAISE EXCEPTION 'v238: device_commands_log missing — apply v20_automation_tables first';
    END IF;
END $$;

ALTER TABLE device_commands_log ADD COLUMN IF NOT EXISTS command_id         TEXT;
ALTER TABLE device_commands_log ADD COLUMN IF NOT EXISTS delivery_state     TEXT;
ALTER TABLE device_commands_log ADD COLUMN IF NOT EXISTS delivery_reason    TEXT;
ALTER TABLE device_commands_log ADD COLUMN IF NOT EXISTS queued_at          TIMESTAMPTZ;
ALTER TABLE device_commands_log ADD COLUMN IF NOT EXISTS published_at       TIMESTAMPTZ;
ALTER TABLE device_commands_log ADD COLUMN IF NOT EXISTS ack_deadline       TIMESTAMPTZ;
ALTER TABLE device_commands_log ADD COLUMN IF NOT EXISTS device_acked_at    TIMESTAMPTZ;
ALTER TABLE device_commands_log ADD COLUMN IF NOT EXISTS device_rejected_at TIMESTAMPTZ;
ALTER TABLE device_commands_log ADD COLUMN IF NOT EXISTS expired_at         TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'public.device_commands_log'::regclass
                     AND conname = 'device_commands_log_delivery_state_chk') THEN
        ALTER TABLE device_commands_log ADD CONSTRAINT device_commands_log_delivery_state_chk
            CHECK (delivery_state IS NULL OR delivery_state IN (
                'queued', 'published', 'device_acked', 'device_rejected',
                'expired', 'publish_failed', 'simulated'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'public.device_commands_log'::regclass
                     AND conname = 'device_commands_log_delivery_ts_chk') THEN
        ALTER TABLE device_commands_log ADD CONSTRAINT device_commands_log_delivery_ts_chk
            CHECK (
                (delivery_state IS NULL
                    OR (command_id IS NOT NULL AND btrim(command_id) <> ''
                        AND queued_at IS NOT NULL AND ack_deadline IS NOT NULL))
                AND (delivery_state IS DISTINCT FROM 'published' OR published_at IS NOT NULL)
                AND (delivery_state IS DISTINCT FROM 'device_acked'
                     OR (published_at IS NOT NULL AND device_acked_at IS NOT NULL))
                AND (delivery_state IS DISTINCT FROM 'device_rejected'
                     OR (published_at IS NOT NULL AND device_rejected_at IS NOT NULL))
                AND (delivery_state IS DISTINCT FROM 'expired' OR expired_at IS NOT NULL)
            );
    END IF;
END $$;

-- One row per (tenant, command id): the ack lookup key, and the upsert target of the
-- queued -> published write.
CREATE UNIQUE INDEX IF NOT EXISTS ux_devcmd_tenant_command
    ON device_commands_log (tenant_id, command_id) WHERE command_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_devcmd_pending_deadline
    ON device_commands_log (tenant_id, ack_deadline)
    WHERE delivery_state IN ('queued', 'published');

CREATE OR REPLACE FUNCTION device_commands_log_delivery_guard()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $fn$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.delivery_state IS NOT NULL
           AND NEW.delivery_state NOT IN ('queued', 'published', 'publish_failed', 'simulated') THEN
            RAISE EXCEPTION 'v238: delivery_state % cannot be inserted (device/expiry states are '
                            'reached by transition only)', NEW.delivery_state
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.command_id IS NOT NULL AND NEW.command_id IS DISTINCT FROM OLD.command_id THEN
        RAISE EXCEPTION 'v238: command_id is immutable once tracked'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.delivery_state IS DISTINCT FROM OLD.delivery_state THEN
        IF NOT (
            (OLD.delivery_state = 'queued'
                AND NEW.delivery_state IN ('published', 'simulated', 'publish_failed', 'expired'))
            OR (OLD.delivery_state = 'published'
                AND NEW.delivery_state IN ('device_acked', 'device_rejected', 'expired'))
        ) THEN
            RAISE EXCEPTION 'v238: illegal delivery transition % -> %',
                COALESCE(OLD.delivery_state, 'NULL'), COALESCE(NEW.delivery_state, 'NULL')
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END
$fn$;

DROP TRIGGER IF EXISTS trg_device_commands_log_delivery_guard ON device_commands_log;
CREATE TRIGGER trg_device_commands_log_delivery_guard
    BEFORE INSERT OR UPDATE ON device_commands_log
    FOR EACH ROW EXECUTE FUNCTION device_commands_log_delivery_guard();

COMMENT ON COLUMN device_commands_log.delivery_state IS
    'v238: queued|published|device_acked|device_rejected|expired|publish_failed|simulated; '
    'NULL = legacy row (untracked). device_* only from published on a signed device ack.';
COMMENT ON COLUMN device_commands_log.command_id IS
    'v238: wire correlation id (MQTT body "id"), echoed by the device ack.';

-- RLS consistency: the extended table must still be tenant-isolated and forced.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class
                   WHERE oid = 'public.device_commands_log'::regclass
                     AND relrowsecurity AND relforcerowsecurity) THEN
        RAISE EXCEPTION 'v238: device_commands_log lost ENABLE/FORCE ROW LEVEL SECURITY';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policy
                   WHERE polrelid = 'public.device_commands_log'::regclass) THEN
        RAISE EXCEPTION 'v238: device_commands_log has no RLS policy';
    END IF;
END $$;

COMMIT;
