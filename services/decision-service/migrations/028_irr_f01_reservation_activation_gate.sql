-- IRR-F01 Phase 1 — the irr_f01_reservation ACTIVATION GATE (single reference implementation).
--
-- Governs whether the irr_f01_reservation capability is ENABLED per environment, from
-- provenance-bearing evidence it CONSUMES (CI live certification + consumer heartbeat) — it never
-- re-runs those checks (no parallel readiness source of truth). Category A (delivery-only, no
-- physical effect): auto-activation is permitted once evidence is valid.
--
-- Deliberately SPECIFIC to irr_f01_reservation — NO generic activation-framework tables
-- (ACTIVATION-GATE-PROD-07 anti-premature-abstraction: extract only after a 2nd Category-A gate).
--
-- Concurrency is CAS on activation_generation; the transition/evidence log is append-only.

-- Current-state projection: one row per environment.
CREATE TABLE IF NOT EXISTS irr_f01_reservation_activation (
  environment_id text PRIMARY KEY,
  state text NOT NULL DEFAULT 'disabled',
  activation_generation bigint NOT NULL DEFAULT 0,
  build_sha char(64) NULL,
  evidence_digest char(64) NULL,
  evaluated_at timestamptz NULL,
  state_expires_at timestamptz NULL,     -- TTL horizon for enabled/degraded; NULL otherwise
  last_reason text NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_irr_act_state CHECK (state IN ('disabled','evaluating','enabled','degraded','revoked')),
  CONSTRAINT ck_irr_act_env CHECK (length(btrim(environment_id)) BETWEEN 1 AND 128),
  CONSTRAINT ck_irr_act_gen CHECK (activation_generation >= 0),
  CONSTRAINT ck_irr_act_build_sha CHECK (build_sha IS NULL OR build_sha ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_irr_act_evidence_digest CHECK (evidence_digest IS NULL OR evidence_digest ~ '^[0-9a-f]{64}$'),
  -- enabled/degraded MUST carry a TTL horizon; terminal/idle states MUST NOT.
  CONSTRAINT ck_irr_act_ttl CHECK (
    (state IN ('enabled','degraded')) = (state_expires_at IS NOT NULL)
  )
);

-- Append-only transition + evidence log: every state change, with the provenance-bearing
-- evidence envelope(s) that justified it. Immutable identity + no-delete (mirrors 005).
CREATE TABLE IF NOT EXISTS irr_f01_reservation_activation_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  environment_id text NOT NULL,
  from_state text NULL,
  to_state text NOT NULL,
  activation_generation bigint NOT NULL,
  build_sha char(64) NULL,
  evidence jsonb NOT NULL DEFAULT '[]'::jsonb,   -- list of {producer,check_name,observed_at,valid_until,result,provenance,environment_id}
  actor text NOT NULL,
  reason text NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_irr_actev_to CHECK (to_state IN ('disabled','evaluating','enabled','degraded','revoked')),
  CONSTRAINT ck_irr_actev_actor CHECK (length(btrim(actor)) BETWEEN 1 AND 256),
  CONSTRAINT ck_irr_actev_reason CHECK (length(btrim(reason)) BETWEEN 1 AND 512),
  CONSTRAINT ck_irr_actev_build_sha CHECK (build_sha IS NULL OR build_sha ~ '^[0-9a-f]{64}$')
);
-- One transition per (environment, generation) — idempotent replay anchor.
CREATE UNIQUE INDEX IF NOT EXISTS uq_irr_activation_event_env_gen
  ON irr_f01_reservation_activation_events (environment_id, activation_generation);
CREATE INDEX IF NOT EXISTS idx_irr_activation_event_env_time
  ON irr_f01_reservation_activation_events (environment_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION irr_f01_reservation_activation_events_immutable()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'irr_f01_reservation_activation_events is append-only';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_irr_activation_events_immutable ON irr_f01_reservation_activation_events;
CREATE TRIGGER trg_irr_activation_events_immutable
  BEFORE UPDATE OR DELETE ON irr_f01_reservation_activation_events
  FOR EACH ROW EXECUTE FUNCTION irr_f01_reservation_activation_events_immutable();

-- The current-projection row itself must be monotonic: generation may only advance by exactly 1
-- and environment_id may never change. State transitions themselves are validated in the
-- application service (which owns the legal-transition matrix); this trigger is the DB backstop
-- against generation rollback / environment rebinding.
CREATE OR REPLACE FUNCTION irr_f01_reservation_activation_guard()
RETURNS trigger AS $$
BEGIN
  IF NEW.environment_id <> OLD.environment_id THEN
    RAISE EXCEPTION 'irr_f01_reservation_activation environment_id is immutable';
  END IF;
  IF NEW.activation_generation <> OLD.activation_generation + 1 THEN
    RAISE EXCEPTION 'irr_f01_reservation_activation generation must advance by exactly 1 (CAS)';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_irr_activation_guard ON irr_f01_reservation_activation;
CREATE TRIGGER trg_irr_activation_guard
  BEFORE UPDATE ON irr_f01_reservation_activation
  FOR EACH ROW EXECUTE FUNCTION irr_f01_reservation_activation_guard();
