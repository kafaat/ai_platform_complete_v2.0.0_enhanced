\set ON_ERROR_STOP on

-- SAHOOL command→event causality live gate.
-- Preconditions: the full migration chain through v18 is applied. v18 retyped
-- events.entity_id to TEXT and DROPped the uuid overload of emit_event, so the
-- entity id is cast ::text here. Casting it ::uuid passes on a v10+v11-only
-- database and fails on every real one with:
--   ERROR: function emit_event(unknown, unknown, uuid, uuid, jsonb, ...) does not exist
-- Reproduced on PostgreSQL 16 against v10+v11+v18.
-- Uses fixed UUIDs intentionally: deterministic fixtures must not depend on
-- test-only functions or optional UUID extensions.

BEGIN;

DO $$
BEGIN
  IF to_regclass('public.commands') IS NULL THEN
    RAISE EXCEPTION 'commands table missing; apply v10 first';
  END IF;
  IF to_regclass('public.events') IS NULL OR to_regclass('public.event_outbox') IS NULL THEN
    RAISE EXCEPTION 'events/outbox tables missing; apply v11 first';
  END IF;
END $$;

-- Clean only the deterministic fixture rows. This is safe for repeat runs.
DELETE FROM events
 WHERE command_id = '11111111-1111-5111-8111-111111111111'::uuid;
DELETE FROM commands
 WHERE command_id = '11111111-1111-5111-8111-111111111111'::uuid;

INSERT INTO commands (
  command_id, command_type, actor_id, tenant_id, payload, source, status
) VALUES (
  '11111111-1111-5111-8111-111111111111'::uuid,
  'cert.command_event_causality',
  'certification-runner',
  'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'::uuid,
  '{}'::jsonb,
  'scheduler',
  'succeeded'
);

-- Capture helper return values in a temporary relation; psql variables are
-- deliberately avoided inside DO blocks because interpolation does not occur
-- inside dollar-quoted PL/pgSQL bodies.
CREATE TEMP TABLE command_event_gate_results (
  first_event_id uuid,
  duplicate_event_id uuid
) ON COMMIT DROP;

INSERT INTO command_event_gate_results(first_event_id)
SELECT emit_event(
  'operation.completed',
  'operation',
  '33333333-3333-4333-8333-333333333333'::text,
  'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'::uuid,
  '{"fixture":"command-event-causality"}'::jsonb,
  'system',
  'certification-runner',
  '11111111-1111-5111-8111-111111111111'::uuid,
  '2026-08-04T00:00:00Z'::timestamptz
);

UPDATE command_event_gate_results
   SET duplicate_event_id = emit_event(
     'operation.completed',
     'operation',
     '33333333-3333-4333-8333-333333333333'::text,
     'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'::uuid,
     '{"fixture":"command-event-causality"}'::jsonb,
     'system',
     'certification-runner',
     '11111111-1111-5111-8111-111111111111'::uuid,
     '2026-08-04T00:00:00Z'::timestamptz
   );

DO $$
DECLARE
  v_first uuid;
  v_duplicate uuid;
  v_command uuid;
  v_events integer;
  v_outbox integer;
BEGIN
  SELECT first_event_id, duplicate_event_id
    INTO v_first, v_duplicate
    FROM command_event_gate_results;

  IF v_first IS NULL THEN
    RAISE EXCEPTION 'first emit_event unexpectedly returned NULL';
  END IF;
  IF v_duplicate IS NOT NULL THEN
    RAISE EXCEPTION 'duplicate emit_event should return NULL, got %', v_duplicate;
  END IF;

  SELECT command_id INTO v_command FROM events WHERE event_id = v_first;
  IF v_command IS DISTINCT FROM '11111111-1111-5111-8111-111111111111'::uuid THEN
    RAISE EXCEPTION 'event command_id mismatch: %', v_command;
  END IF;

  SELECT count(*) INTO v_events
    FROM events
   WHERE command_id = '11111111-1111-5111-8111-111111111111'::uuid
     AND event_type = 'operation.completed';
  SELECT count(*) INTO v_outbox
    FROM event_outbox o
    JOIN events e ON e.event_id = o.event_id
   WHERE e.command_id = '11111111-1111-5111-8111-111111111111'::uuid
     AND e.event_type = 'operation.completed';

  IF v_events <> 1 OR v_outbox <> 1 THEN
    RAISE EXCEPTION 'dedup failed: events %, outbox %', v_events, v_outbox;
  END IF;
END $$;

-- Invalid causality must fail at the FK. Catch the expected violation so the
-- gate itself can continue and assert that no row leaked through.
DO $$
BEGIN
  BEGIN
    INSERT INTO events (
      event_type, entity_type, entity_id, tenant_id, command_id, payload, source
    ) VALUES (
      'operation.completed', 'operation',
      '44444444-4444-4444-8444-444444444444'::text,
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'::uuid,
      '99999999-9999-4999-8999-999999999999'::uuid,
      '{}'::jsonb, 'system'
    );
    RAISE EXCEPTION 'invalid command_id unexpectedly accepted';
  EXCEPTION WHEN foreign_key_violation THEN
    NULL; -- expected
  END;
END $$;

-- Rollback safety: command/event/outbox created in a savepoint and rolled back
-- must all disappear together.
SAVEPOINT rollback_probe;
INSERT INTO commands (
  command_id, command_type, actor_id, tenant_id, payload, source
) VALUES (
  '55555555-5555-4555-8555-555555555555'::uuid,
  'cert.rollback_probe', 'certification-runner',
  'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'::uuid,
  '{}'::jsonb, 'scheduler'
);
SELECT emit_event(
  'operation.completed', 'operation',
  '66666666-6666-4666-8666-666666666666'::text,
  'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'::uuid,
  '{"fixture":"rollback"}'::jsonb, 'system',
  'certification-runner',
  '55555555-5555-4555-8555-555555555555'::uuid,
  '2026-08-04T00:01:00Z'::timestamptz
);
ROLLBACK TO SAVEPOINT rollback_probe;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM commands WHERE command_id='55555555-5555-4555-8555-555555555555'::uuid)
     OR EXISTS (SELECT 1 FROM events WHERE command_id='55555555-5555-4555-8555-555555555555'::uuid) THEN
    RAISE EXCEPTION 'rollback probe leaked command/event rows';
  END IF;
END $$;

ROLLBACK;

\echo 'PASS command_event_causality_live_gate'
