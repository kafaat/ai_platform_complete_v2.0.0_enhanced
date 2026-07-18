-- Phase 2 — the satellite_cdse ACTIVATION GATE (the SECOND, independent Category-A reference).
--
-- Governs whether CDSE is the ACTIVE imagery source for an environment, from provenance-bearing
-- evidence it CONSUMES (raster-service: CDSE credentials present + a successful live scene probe).
-- Category A (delivery/data, no physical effect): when enabled CDSE is used, otherwise the runtime
-- falls back to Element84 — the enforcement is a SOURCE SELECTION, not a refusal.
--
-- Deliberately a SEPARATE, DUPLICATED implementation from irr_f01_reservation (migration 028) —
-- ACTIVATION-GATE-PROD-07 anti-premature-abstraction: only after TWO independent Category-A gates
-- exist do we extract the proven-shared machinery (Phase 3). The shape mirrors 028 on purpose so
-- that comparison reveals the true seams; the differences are the evidence and the enforcement.

CREATE TABLE IF NOT EXISTS satellite_cdse_activation (
  environment_id text PRIMARY KEY,
  state text NOT NULL DEFAULT 'disabled',
  activation_generation bigint NOT NULL DEFAULT 0,
  build_sha char(64) NULL,
  evidence_digest char(64) NULL,
  evaluated_at timestamptz NULL,
  state_expires_at timestamptz NULL,
  last_reason text NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_cdse_act_state CHECK (state IN ('disabled','evaluating','enabled','degraded','revoked')),
  CONSTRAINT ck_cdse_act_env CHECK (length(btrim(environment_id)) BETWEEN 1 AND 128),
  CONSTRAINT ck_cdse_act_gen CHECK (activation_generation >= 0),
  CONSTRAINT ck_cdse_act_build_sha CHECK (build_sha IS NULL OR build_sha ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_cdse_act_evidence_digest CHECK (evidence_digest IS NULL OR evidence_digest ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_cdse_act_ttl CHECK (
    (state IN ('enabled','degraded')) = (state_expires_at IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS satellite_cdse_activation_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  environment_id text NOT NULL,
  from_state text NULL,
  to_state text NOT NULL,
  activation_generation bigint NOT NULL,
  build_sha char(64) NULL,
  evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
  actor text NOT NULL,
  reason text NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_cdse_actev_to CHECK (to_state IN ('disabled','evaluating','enabled','degraded','revoked')),
  CONSTRAINT ck_cdse_actev_actor CHECK (length(btrim(actor)) BETWEEN 1 AND 256),
  CONSTRAINT ck_cdse_actev_reason CHECK (length(btrim(reason)) BETWEEN 1 AND 512),
  CONSTRAINT ck_cdse_actev_build_sha CHECK (build_sha IS NULL OR build_sha ~ '^[0-9a-f]{64}$')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_cdse_activation_event_env_gen
  ON satellite_cdse_activation_events (environment_id, activation_generation);
CREATE INDEX IF NOT EXISTS idx_cdse_activation_event_env_time
  ON satellite_cdse_activation_events (environment_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION satellite_cdse_activation_events_immutable()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'satellite_cdse_activation_events is append-only';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_cdse_activation_events_immutable ON satellite_cdse_activation_events;
CREATE TRIGGER trg_cdse_activation_events_immutable
  BEFORE UPDATE OR DELETE ON satellite_cdse_activation_events
  FOR EACH ROW EXECUTE FUNCTION satellite_cdse_activation_events_immutable();

CREATE OR REPLACE FUNCTION satellite_cdse_activation_guard()
RETURNS trigger AS $$
BEGIN
  IF NEW.environment_id <> OLD.environment_id THEN
    RAISE EXCEPTION 'satellite_cdse_activation environment_id is immutable';
  END IF;
  IF NEW.activation_generation <> OLD.activation_generation + 1 THEN
    RAISE EXCEPTION 'satellite_cdse_activation generation must advance by exactly 1 (CAS)';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_cdse_activation_guard ON satellite_cdse_activation;
CREATE TRIGGER trg_cdse_activation_guard
  BEFORE UPDATE ON satellite_cdse_activation
  FOR EACH ROW EXECUTE FUNCTION satellite_cdse_activation_guard();
