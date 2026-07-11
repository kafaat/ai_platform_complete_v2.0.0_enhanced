-- WX-10.9 — Approved Decision -> Execution Plan boundary.
-- Additive/idempotent. An execution plan is a persisted, non-executing projection of an
-- approved decision. It MUST NOT dispatch, create tasks, or command equipment.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS decision_execution_plans (
  execution_plan_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  decision_id text NOT NULL,
  review_id text NOT NULL,
  candidate_lineage_id text NOT NULL,
  operation_type text NOT NULL,
  planned_start timestamptz NULL,
  planned_end timestamptz NULL,
  target_zone_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  required_resources jsonb NOT NULL DEFAULT '[]'::jsonb,
  constraints jsonb NOT NULL DEFAULT '{}'::jsonb,
  safety_conditions jsonb NOT NULL DEFAULT '{}'::jsonb,
  weather_window_reference jsonb NULL,
  status text NOT NULL DEFAULT 'planned',
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_execution_plan_status CHECK (status = 'planned'),
  CONSTRAINT ck_execution_plan_operation_type CHECK (length(btrim(operation_type)) > 0),
  CONSTRAINT ck_execution_plan_created_by CHECK (length(btrim(created_by)) > 0),
  CONSTRAINT ck_execution_plan_window CHECK (
    planned_start IS NULL OR planned_end IS NULL OR planned_end > planned_start
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_execution_plan_tenant_decision
  ON decision_execution_plans (tenant_id, decision_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_execution_plan_tenant_idem
  ON decision_execution_plans (tenant_id, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_execution_plan_tenant_status_created
  ON decision_execution_plans (tenant_id, status, created_at DESC);

CREATE OR REPLACE FUNCTION decision_execution_plans_append_only()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'decision_execution_plans is append-only (% not allowed)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_decision_execution_plans_append_only ON decision_execution_plans;
CREATE TRIGGER trg_decision_execution_plans_append_only
  BEFORE UPDATE OR DELETE ON decision_execution_plans
  FOR EACH ROW EXECUTE FUNCTION decision_execution_plans_append_only();
