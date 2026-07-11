-- WX-10.13 — verified outcome -> immutable learning attribution lineage.
-- Attribution only: no model fitting, reward mutation, or automatic redispatch.
CREATE TABLE IF NOT EXISTS decision_learning_attributions (
  learning_attribution_id text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  outcome_id text NOT NULL,
  decision_id text NOT NULL,
  execution_request_id text NOT NULL,
  model_id text NOT NULL,
  feature_set_id text NULL,
  attribution_method text NOT NULL DEFAULT 'verified_outcome',
  label text NOT NULL,
  weight double precision NOT NULL DEFAULT 1.0,
  evidence_snapshot_id text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  learning_state text NOT NULL DEFAULT 'attributed',
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  attributed_by text NOT NULL,
  attributed_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_learning_attribution_method CHECK (attribution_method = 'verified_outcome'),
  CONSTRAINT ck_learning_attribution_label CHECK (label IN ('success','failure')),
  CONSTRAINT ck_learning_attribution_weight CHECK (weight > 0 AND weight <= 1),
  CONSTRAINT ck_learning_attribution_state CHECK (learning_state = 'attributed')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_learning_attribution_idempotency
  ON decision_learning_attributions (tenant_id, idempotency_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_learning_attribution_outcome_model_feature
  ON decision_learning_attributions (tenant_id, outcome_id, model_id, COALESCE(feature_set_id, ''));
CREATE INDEX IF NOT EXISTS idx_learning_attribution_model_time
  ON decision_learning_attributions (tenant_id, model_id, attributed_at DESC);

CREATE OR REPLACE FUNCTION decision_learning_attribution_append_only()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'learning attribution is append-only';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_decision_learning_attribution_append_only ON decision_learning_attributions;
CREATE TRIGGER trg_decision_learning_attribution_append_only
  BEFORE UPDATE OR DELETE ON decision_learning_attributions
  FOR EACH ROW EXECUTE FUNCTION decision_learning_attribution_append_only();
