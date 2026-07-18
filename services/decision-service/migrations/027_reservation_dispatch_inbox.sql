-- IRR-F01 Gate B-delivery (thin inbox) — durable, deduplicated landing zone for irrigation
-- reservation dispatch INTENTS delivered from the platform outbox
-- (irrigation.reservation.dispatch_requested / _failed).
--
-- This records DELIVERY (a receipt), NOT fulfillment: it deliberately does NOT create a
-- decision_execution_request. Turning a received intent into an authorized execution request
-- is a later, explicit gate (link-to-authorized-execution), gated on WX-10 authorization —
-- never auto-executed here. This keeps "intent ≠ delivery ≠ execution" honest.
--
-- Additive/idempotent, mirroring the append-preserving + immutable-identity shape of
-- 005_execution_request.sql. Tenant scoping is by explicit predicate (decision-service SoR
-- convention), same as the other execution-chain tables.

CREATE TABLE IF NOT EXISTS decision_reservation_dispatch_inbox (
  inbox_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  source_event_id text NOT NULL,          -- the platform events.event_id — the dedup anchor
  event_type text NOT NULL,
  evaluation_id text NULL,
  reservation_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  execution_ref_type text NULL,
  execution_ref_id text NULL,
  correlation_id text NULL,
  causation_id text NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  dispatch_state text NOT NULL,           -- received | failure_notice (delivery-only lifecycle)
  receipt_id text NOT NULL,
  request_hash text NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_inbox_state CHECK (dispatch_state IN ('received','failure_notice')),
  CONSTRAINT ck_inbox_event_type CHECK (event_type IN (
    'irrigation.reservation.dispatch_requested','irrigation.reservation.dispatch_failed')),
  CONSTRAINT ck_inbox_source_event CHECK (length(btrim(source_event_id)) BETWEEN 1 AND 256),
  CONSTRAINT ck_inbox_receipt CHECK (length(btrim(receipt_id)) > 0),
  CONSTRAINT ck_inbox_hash CHECK (request_hash ~ '^[0-9a-f]{64}$')
);

-- Idempotent delivery: one row per (tenant, source event) — a redelivered outbox event is a
-- no-op that returns the ORIGINAL receipt.
CREATE UNIQUE INDEX IF NOT EXISTS uq_reservation_inbox_tenant_event
  ON decision_reservation_dispatch_inbox (tenant_id, source_event_id);
CREATE INDEX IF NOT EXISTS idx_reservation_inbox_tenant_state
  ON decision_reservation_dispatch_inbox (tenant_id, dispatch_state, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_reservation_inbox_execution_ref
  ON decision_reservation_dispatch_inbox (tenant_id, execution_ref_type, execution_ref_id);

-- The delivery receipt is immutable and append-preserving (mirrors 005).
CREATE OR REPLACE FUNCTION decision_reservation_inbox_immutable_identity()
RETURNS trigger AS $$
BEGIN
  IF NEW.inbox_id <> OLD.inbox_id
     OR NEW.tenant_id <> OLD.tenant_id
     OR NEW.source_event_id <> OLD.source_event_id
     OR NEW.event_type <> OLD.event_type
     OR NEW.payload <> OLD.payload
     OR NEW.dispatch_state <> OLD.dispatch_state
     OR NEW.receipt_id <> OLD.receipt_id
     OR NEW.request_hash <> OLD.request_hash
     OR NEW.received_at <> OLD.received_at THEN
    RAISE EXCEPTION 'decision_reservation_dispatch_inbox identity is immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_reservation_inbox_immutable ON decision_reservation_dispatch_inbox;
CREATE TRIGGER trg_reservation_inbox_immutable
  BEFORE UPDATE ON decision_reservation_dispatch_inbox
  FOR EACH ROW EXECUTE FUNCTION decision_reservation_inbox_immutable_identity();

CREATE OR REPLACE FUNCTION decision_reservation_inbox_no_delete()
RETURNS trigger AS $$ BEGIN
  RAISE EXCEPTION 'decision_reservation_dispatch_inbox is append-preserving';
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_reservation_inbox_no_delete ON decision_reservation_dispatch_inbox;
CREATE TRIGGER trg_reservation_inbox_no_delete
  BEFORE DELETE ON decision_reservation_dispatch_inbox
  FOR EACH ROW EXECUTE FUNCTION decision_reservation_inbox_no_delete();

-- Consumer liveness so an activation gate can verify the delivery consumer is actually running
-- BEFORE the feature is flipped on (feeds IRR-F01-FEATURE-ACTIVATION). Single-row-per-consumer
-- projection; last_seen_at advances on every ingest.
CREATE TABLE IF NOT EXISTS decision_consumer_heartbeats (
  consumer_name text PRIMARY KEY,
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  last_event_id text NULL,
  processed_count bigint NOT NULL DEFAULT 0,
  CONSTRAINT ck_heartbeat_name CHECK (length(btrim(consumer_name)) BETWEEN 1 AND 128)
);
