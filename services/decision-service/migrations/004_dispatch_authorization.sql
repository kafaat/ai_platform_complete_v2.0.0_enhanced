-- WX-10.10 — Execution Plan -> Dispatch Authorization boundary.
-- Additive/idempotent. Authorization proves that a planned execution plan may proceed to a
-- later dispatch increment. It MUST NOT create tasks, issue equipment commands, or dispatch.

CREATE TABLE IF NOT EXISTS decision_dispatch_authorizations (
  dispatch_authorization_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  execution_plan_id text NOT NULL,
  decision_id text NOT NULL,
  review_id text NOT NULL,
  candidate_lineage_id text NOT NULL,
  expected_plan_state text NOT NULL,
  policy_version text NOT NULL,
  weather_snapshot_id text NOT NULL,
  resource_snapshot_id text NOT NULL,
  authorization_reason text NULL,
  status text NOT NULL DEFAULT 'authorized',
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  authorized_by text NOT NULL,
  authorized_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_dispatch_authorization_status CHECK (status = 'authorized'),
  CONSTRAINT ck_dispatch_authorization_plan_state CHECK (expected_plan_state = 'planned'),
  CONSTRAINT ck_dispatch_authorization_policy CHECK (length(btrim(policy_version)) > 0),
  CONSTRAINT ck_dispatch_authorization_weather_snapshot CHECK (length(btrim(weather_snapshot_id)) > 0),
  CONSTRAINT ck_dispatch_authorization_resource_snapshot CHECK (length(btrim(resource_snapshot_id)) > 0),
  CONSTRAINT ck_dispatch_authorization_actor CHECK (length(btrim(authorized_by)) > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dispatch_authorization_tenant_plan
  ON decision_dispatch_authorizations (tenant_id, execution_plan_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_dispatch_authorization_tenant_idem
  ON decision_dispatch_authorizations (tenant_id, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_dispatch_authorization_tenant_created
  ON decision_dispatch_authorizations (tenant_id, authorized_at DESC);

CREATE OR REPLACE FUNCTION decision_dispatch_authorizations_append_only()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'decision_dispatch_authorizations is append-only (% not allowed)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_decision_dispatch_authorizations_append_only
  ON decision_dispatch_authorizations;
CREATE TRIGGER trg_decision_dispatch_authorizations_append_only
  BEFORE UPDATE OR DELETE ON decision_dispatch_authorizations
  FOR EACH ROW EXECUTE FUNCTION decision_dispatch_authorizations_append_only();
