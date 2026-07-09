-- Decision-service System-of-Record migration foundation.
-- Safe to apply before traffic cutover: platform remains the writer until DECISION_SERVICE_SOR_ENABLED=true.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS decision_record (
  decision_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  field_id text NULL,
  decision_type text NOT NULL DEFAULT 'recommendation',
  region text NULL,
  stage text NOT NULL DEFAULT 'decision',
  decision_value jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence double precision NULL,
  created_by text NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_decision_record_tenant_field_created
  ON decision_record (tenant_id, field_id, created_at DESC);

CREATE TABLE IF NOT EXISTS dispatch_decisions (
  decision_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  recommendation_id text NOT NULL,
  action_type text NOT NULL,
  risk_level text NOT NULL DEFAULT 'MEDIUM',
  field_id text NULL,
  state text NOT NULL DEFAULT 'pending_approval',
  command jsonb NULL,
  created_by text NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dispatch_decisions_tenant_state
  ON dispatch_decisions (tenant_id, state, created_at DESC);

CREATE TABLE IF NOT EXISTS outcome_record (
  outcome_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  decision_id text NOT NULL,
  field_id text NULL,
  region text NULL,
  planned jsonb NOT NULL DEFAULT '{}'::jsonb,
  actual jsonb NOT NULL DEFAULT '{}'::jsonb,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  success boolean NULL,
  created_by text NULL,
  idempotency_key text NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_outcome_record_tenant_idempotency
  ON outcome_record (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_outcome_record_tenant_decision
  ON outcome_record (tenant_id, decision_id, created_at DESC);

CREATE TABLE IF NOT EXISTS recommendation_outcomes (
  tenant_id uuid NOT NULL,
  recommendation_id text NOT NULL,
  decision_id text NULL,
  field_id text NULL,
  season_id text NULL,
  outcome text NOT NULL DEFAULT 'pending',
  confidence double precision NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, recommendation_id)
);

CREATE TABLE IF NOT EXISTS online_learning_updates (
  update_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  model_id text NOT NULL,
  feature_set_id text NULL,
  learning_rate double precision NOT NULL DEFAULT 0.01,
  sample_count integer NOT NULL DEFAULT 0,
  label_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  drift_score double precision NOT NULL DEFAULT 0,
  action text NULL,
  source_type text NULL,
  source_id text NULL,
  field_id text NULL,
  season_id text NULL,
  recommendation_id text NULL,
  decision_id text NULL,
  evidence_snapshot_id text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_learning_traceable CHECK (
    (source_type IS NOT NULL AND source_id IS NOT NULL)
    OR recommendation_id IS NOT NULL
    OR decision_id IS NOT NULL
    OR evidence_snapshot_id IS NOT NULL
  )
);

CREATE TABLE IF NOT EXISTS decision_outbox_events (
  event_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  event_type text NOT NULL,
  aggregate_type text NOT NULL,
  aggregate_id text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz NULL
);
CREATE INDEX IF NOT EXISTS idx_decision_outbox_pending
  ON decision_outbox_events (status, created_at) WHERE status = 'pending';
