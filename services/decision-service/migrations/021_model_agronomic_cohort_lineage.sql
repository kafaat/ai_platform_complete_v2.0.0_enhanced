-- (delivered as 022; landed as 021 on the reconciled numbering)
-- WX-11.7 — propagate immutable agronomic cohort lineage through evaluation, promotion, and activation.
-- The cohort manifest is derived server-side from the calibrated learning dataset; clients cannot substitute it.

ALTER TABLE decision_model_evaluation_runs
  ADD COLUMN IF NOT EXISTS agronomic_cohorts jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS agronomic_cohort_fingerprint text;

ALTER TABLE decision_model_promotion_decisions
  ADD COLUMN IF NOT EXISTS agronomic_cohorts jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS agronomic_cohort_fingerprint text;

ALTER TABLE decision_model_activation_requests
  ADD COLUMN IF NOT EXISTS agronomic_cohorts jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS agronomic_cohort_fingerprint text;

ALTER TABLE decision_model_evaluation_runs
  DROP CONSTRAINT IF EXISTS ck_model_eval_cohort_fingerprint;
ALTER TABLE decision_model_evaluation_runs
  ADD CONSTRAINT ck_model_eval_cohort_fingerprint
  CHECK (agronomic_cohort_fingerprint IS NULL OR agronomic_cohort_fingerprint ~ '^[a-f0-9]{64}$');

ALTER TABLE decision_model_promotion_decisions
  DROP CONSTRAINT IF EXISTS ck_model_promotion_cohort_fingerprint;
ALTER TABLE decision_model_promotion_decisions
  ADD CONSTRAINT ck_model_promotion_cohort_fingerprint
  CHECK (agronomic_cohort_fingerprint IS NULL OR agronomic_cohort_fingerprint ~ '^[a-f0-9]{64}$');

ALTER TABLE decision_model_activation_requests
  DROP CONSTRAINT IF EXISTS ck_model_activation_cohort_fingerprint;
ALTER TABLE decision_model_activation_requests
  ADD CONSTRAINT ck_model_activation_cohort_fingerprint
  CHECK (agronomic_cohort_fingerprint IS NULL OR agronomic_cohort_fingerprint ~ '^[a-f0-9]{64}$');

CREATE OR REPLACE FUNCTION enforce_model_promotion_cohort_lineage()
RETURNS trigger AS $$
DECLARE src decision_model_evaluation_runs%ROWTYPE;
BEGIN
  SELECT * INTO src FROM decision_model_evaluation_runs
   WHERE tenant_id = NEW.tenant_id AND evaluation_run_id = NEW.evaluation_run_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'source evaluation run not found'; END IF;
  IF NEW.agronomic_cohorts IS DISTINCT FROM src.agronomic_cohorts
     OR NEW.agronomic_cohort_fingerprint IS DISTINCT FROM src.agronomic_cohort_fingerprint THEN
    RAISE EXCEPTION 'promotion agronomic cohort lineage must match evaluation';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_model_promotion_cohort_lineage ON decision_model_promotion_decisions;
CREATE TRIGGER trg_model_promotion_cohort_lineage
  BEFORE INSERT ON decision_model_promotion_decisions
  FOR EACH ROW EXECUTE FUNCTION enforce_model_promotion_cohort_lineage();

CREATE OR REPLACE FUNCTION enforce_model_activation_cohort_lineage()
RETURNS trigger AS $$
DECLARE src decision_model_promotion_decisions%ROWTYPE;
BEGIN
  SELECT * INTO src FROM decision_model_promotion_decisions
   WHERE tenant_id = NEW.tenant_id AND promotion_decision_id = NEW.promotion_decision_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'source promotion decision not found'; END IF;
  IF NEW.agronomic_cohorts IS DISTINCT FROM src.agronomic_cohorts
     OR NEW.agronomic_cohort_fingerprint IS DISTINCT FROM src.agronomic_cohort_fingerprint THEN
    RAISE EXCEPTION 'activation agronomic cohort lineage must match promotion';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_model_activation_cohort_lineage ON decision_model_activation_requests;
CREATE TRIGGER trg_model_activation_cohort_lineage
  BEFORE INSERT ON decision_model_activation_requests
  FOR EACH ROW EXECUTE FUNCTION enforce_model_activation_cohort_lineage();
