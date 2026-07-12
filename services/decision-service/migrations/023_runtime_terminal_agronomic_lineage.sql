-- (delivered as 024; landed as 023 on the reconciled numbering)
-- Complete agronomic lineage across rollback and terminal runtime receipts.
ALTER TABLE decision_model_monitoring_snapshots
  ADD COLUMN IF NOT EXISTS source_transition_type text NOT NULL DEFAULT 'activation';

DO $$ BEGIN
  ALTER TABLE decision_model_monitoring_snapshots
    ADD CONSTRAINT ck_monitoring_source_transition_type
    CHECK (source_transition_type IN ('activation','rollback'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE OR REPLACE FUNCTION decision_assert_rollback_command_cohorts() RETURNS trigger AS $$
DECLARE src record;
BEGIN
  SELECT agronomic_cohorts, agronomic_cohort_fingerprint INTO src
  FROM decision_model_registry_activation_receipts
  WHERE tenant_id=NEW.tenant_id AND activation_receipt_id=NEW.activation_receipt_id;
  IF NOT FOUND OR NEW.agronomic_cohorts IS DISTINCT FROM src.agronomic_cohorts
     OR NEW.agronomic_cohort_fingerprint IS DISTINCT FROM src.agronomic_cohort_fingerprint THEN
    RAISE EXCEPTION 'rollback command agronomic cohorts must match activation receipt';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_rollback_command_agronomic_cohorts ON decision_model_registry_rollback_commands;
CREATE TRIGGER trg_rollback_command_agronomic_cohorts BEFORE INSERT ON decision_model_registry_rollback_commands
FOR EACH ROW EXECUTE FUNCTION decision_assert_rollback_command_cohorts();

CREATE OR REPLACE FUNCTION decision_assert_rollback_receipt_cohorts() RETURNS trigger AS $$
DECLARE src record;
BEGIN
  SELECT agronomic_cohorts, agronomic_cohort_fingerprint INTO src
  FROM decision_model_registry_rollback_commands
  WHERE tenant_id=NEW.tenant_id AND rollback_command_id=NEW.rollback_command_id;
  IF NOT FOUND OR NEW.agronomic_cohorts IS DISTINCT FROM src.agronomic_cohorts
     OR NEW.agronomic_cohort_fingerprint IS DISTINCT FROM src.agronomic_cohort_fingerprint THEN
    RAISE EXCEPTION 'rollback receipt agronomic cohorts must match rollback command';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_rollback_receipt_agronomic_cohorts ON decision_model_registry_rollback_receipts;
CREATE TRIGGER trg_rollback_receipt_agronomic_cohorts BEFORE INSERT ON decision_model_registry_rollback_receipts
FOR EACH ROW EXECUTE FUNCTION decision_assert_rollback_receipt_cohorts();

CREATE OR REPLACE FUNCTION decision_assert_rollout_receipt_cohorts() RETURNS trigger AS $$
DECLARE src record;
BEGIN
  SELECT agronomic_cohorts, agronomic_cohort_fingerprint INTO src
  FROM decision_model_rollout_plans
  WHERE tenant_id=NEW.tenant_id AND rollout_plan_id=NEW.rollout_plan_id;
  IF NOT FOUND OR NEW.agronomic_cohorts IS DISTINCT FROM src.agronomic_cohorts
     OR NEW.agronomic_cohort_fingerprint IS DISTINCT FROM src.agronomic_cohort_fingerprint THEN
    RAISE EXCEPTION 'rollout receipt agronomic cohorts must match rollout plan';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_rollout_receipt_agronomic_cohorts ON decision_model_rollout_receipts;
CREATE TRIGGER trg_rollout_receipt_agronomic_cohorts BEFORE INSERT ON decision_model_rollout_receipts
FOR EACH ROW EXECUTE FUNCTION decision_assert_rollout_receipt_cohorts();

CREATE OR REPLACE FUNCTION decision_assert_retraining_dispatch_cohorts() RETURNS trigger AS $$
DECLARE src record;
BEGIN
  SELECT agronomic_cohorts, agronomic_cohort_fingerprint INTO src
  FROM decision_model_retraining_requests
  WHERE tenant_id=NEW.tenant_id AND retraining_request_id=NEW.retraining_request_id;
  IF NOT FOUND OR NEW.agronomic_cohorts IS DISTINCT FROM src.agronomic_cohorts
     OR NEW.agronomic_cohort_fingerprint IS DISTINCT FROM src.agronomic_cohort_fingerprint THEN
    RAISE EXCEPTION 'retraining dispatch receipt agronomic cohorts must match request';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_retraining_dispatch_agronomic_cohorts ON decision_model_retraining_dispatch_receipts;
CREATE TRIGGER trg_retraining_dispatch_agronomic_cohorts BEFORE INSERT ON decision_model_retraining_dispatch_receipts
FOR EACH ROW EXECUTE FUNCTION decision_assert_retraining_dispatch_cohorts();

-- Monitoring may follow either the latest activation or the latest rollback transition.
CREATE OR REPLACE FUNCTION decision_assert_monitoring_cohorts() RETURNS trigger AS $$
DECLARE src record;
BEGIN
  IF NEW.source_receipt_id IS NULL THEN RAISE EXCEPTION 'monitoring snapshot requires source_receipt_id'; END IF;
  IF NEW.source_transition_type='activation' THEN
    SELECT c.model_id,c.feature_set_id,c.target_environment,r.agronomic_cohorts,r.agronomic_cohort_fingerprint INTO src
    FROM decision_model_registry_activation_receipts r
    JOIN decision_model_registry_activation_commands c USING(activation_command_id)
    WHERE r.tenant_id=NEW.tenant_id AND r.activation_receipt_id=NEW.source_receipt_id AND r.receipt_state='activated';
  ELSE
    SELECT c.model_id,c.feature_set_id,c.target_environment,r.agronomic_cohorts,r.agronomic_cohort_fingerprint INTO src
    FROM decision_model_registry_rollback_receipts r
    JOIN decision_model_registry_rollback_commands rb USING(rollback_command_id)
    JOIN decision_model_registry_activation_commands c ON c.activation_command_id=rb.activation_command_id
    WHERE r.tenant_id=NEW.tenant_id AND r.rollback_receipt_id=NEW.source_receipt_id AND r.receipt_state='rolled_back';
  END IF;
  IF NOT FOUND OR NEW.model_id IS DISTINCT FROM src.model_id OR NEW.feature_set_id IS DISTINCT FROM src.feature_set_id
     OR NEW.target_environment IS DISTINCT FROM src.target_environment
     OR NEW.agronomic_cohorts IS DISTINCT FROM src.agronomic_cohorts
     OR NEW.agronomic_cohort_fingerprint IS DISTINCT FROM src.agronomic_cohort_fingerprint THEN
    RAISE EXCEPTION 'monitoring snapshot must match latest runtime transition and agronomic cohorts';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
