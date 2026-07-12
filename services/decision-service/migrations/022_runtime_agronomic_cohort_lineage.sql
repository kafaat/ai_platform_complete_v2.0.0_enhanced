-- (delivered as 023; landed as 022 on the reconciled numbering)
-- Runtime agronomic cohort lineage: propagate the evaluated agricultural population through
-- activation, verification, rollout, monitoring and retraining. All values are inherited from
-- authoritative upstream evidence; clients cannot substitute a different cohort manifest.

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'decision_model_activation_reviews',
    'decision_model_registry_activation_commands',
    'decision_model_registry_activation_receipts',
    'decision_model_registry_rollback_commands',
    'decision_model_registry_rollback_receipts',
    'decision_model_post_activation_verifications',
    'decision_model_rollout_plans',
    'decision_model_rollout_receipts',
    'decision_model_monitoring_snapshots',
    'decision_model_retraining_requests',
    'decision_model_retraining_dispatch_receipts'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS agronomic_cohorts jsonb NOT NULL DEFAULT ''{}''::jsonb', t);
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS agronomic_cohort_fingerprint text', t);
  END LOOP;
END $$;

ALTER TABLE decision_model_monitoring_snapshots
  ADD COLUMN IF NOT EXISTS source_receipt_id text;
ALTER TABLE decision_model_retraining_requests
  ADD COLUMN IF NOT EXISTS source_monitoring_snapshot_id text,
  ADD COLUMN IF NOT EXISTS target_environment text NOT NULL DEFAULT 'production';

DO $$
DECLARE t text; cname text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'decision_model_activation_reviews','decision_model_registry_activation_commands',
    'decision_model_registry_activation_receipts','decision_model_registry_rollback_commands',
    'decision_model_registry_rollback_receipts','decision_model_post_activation_verifications',
    'decision_model_rollout_plans','decision_model_rollout_receipts',
    'decision_model_monitoring_snapshots','decision_model_retraining_requests',
    'decision_model_retraining_dispatch_receipts'
  ] LOOP
    cname := 'ck_' || replace(t, 'decision_model_', '') || '_agronomic_fp';
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname=cname) THEN
      EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I CHECK (agronomic_cohort_fingerprint IS NULL OR agronomic_cohort_fingerprint ~ ''^[a-f0-9]{64}$'')', t, cname);
    END IF;
  END LOOP;
END $$;

CREATE OR REPLACE FUNCTION decision_assert_activation_review_cohorts() RETURNS trigger AS $$
DECLARE src record;
BEGIN
  SELECT agronomic_cohorts, agronomic_cohort_fingerprint INTO src
  FROM decision_model_activation_requests
  WHERE tenant_id=NEW.tenant_id AND activation_request_id=NEW.activation_request_id;
  IF NOT FOUND OR NEW.agronomic_cohorts IS DISTINCT FROM src.agronomic_cohorts
     OR NEW.agronomic_cohort_fingerprint IS DISTINCT FROM src.agronomic_cohort_fingerprint THEN
    RAISE EXCEPTION 'activation review agronomic cohorts must match activation request';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_activation_review_agronomic_cohorts ON decision_model_activation_reviews;
CREATE TRIGGER trg_activation_review_agronomic_cohorts BEFORE INSERT ON decision_model_activation_reviews
FOR EACH ROW EXECUTE FUNCTION decision_assert_activation_review_cohorts();

CREATE OR REPLACE FUNCTION decision_assert_activation_command_cohorts() RETURNS trigger AS $$
DECLARE src record;
BEGIN
  SELECT agronomic_cohorts, agronomic_cohort_fingerprint INTO src
  FROM decision_model_activation_reviews
  WHERE tenant_id=NEW.tenant_id AND activation_review_id=NEW.activation_review_id;
  IF NOT FOUND OR NEW.agronomic_cohorts IS DISTINCT FROM src.agronomic_cohorts
     OR NEW.agronomic_cohort_fingerprint IS DISTINCT FROM src.agronomic_cohort_fingerprint THEN
    RAISE EXCEPTION 'activation command agronomic cohorts must match review';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_activation_command_agronomic_cohorts ON decision_model_registry_activation_commands;
CREATE TRIGGER trg_activation_command_agronomic_cohorts BEFORE INSERT ON decision_model_registry_activation_commands
FOR EACH ROW EXECUTE FUNCTION decision_assert_activation_command_cohorts();

CREATE OR REPLACE FUNCTION decision_assert_activation_receipt_cohorts() RETURNS trigger AS $$
DECLARE src record;
BEGIN
  SELECT agronomic_cohorts, agronomic_cohort_fingerprint INTO src
  FROM decision_model_registry_activation_commands
  WHERE tenant_id=NEW.tenant_id AND activation_command_id=NEW.activation_command_id;
  IF NOT FOUND OR NEW.agronomic_cohorts IS DISTINCT FROM src.agronomic_cohorts
     OR NEW.agronomic_cohort_fingerprint IS DISTINCT FROM src.agronomic_cohort_fingerprint THEN
    RAISE EXCEPTION 'activation receipt agronomic cohorts must match command';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_activation_receipt_agronomic_cohorts ON decision_model_registry_activation_receipts;
CREATE TRIGGER trg_activation_receipt_agronomic_cohorts BEFORE INSERT ON decision_model_registry_activation_receipts
FOR EACH ROW EXECUTE FUNCTION decision_assert_activation_receipt_cohorts();

CREATE OR REPLACE FUNCTION decision_assert_verification_cohorts() RETURNS trigger AS $$
DECLARE src record;
BEGIN
  SELECT agronomic_cohorts, agronomic_cohort_fingerprint INTO src
  FROM decision_model_registry_activation_receipts
  WHERE tenant_id=NEW.tenant_id AND activation_receipt_id=NEW.activation_receipt_id;
  IF NOT FOUND OR NEW.agronomic_cohorts IS DISTINCT FROM src.agronomic_cohorts
     OR NEW.agronomic_cohort_fingerprint IS DISTINCT FROM src.agronomic_cohort_fingerprint THEN
    RAISE EXCEPTION 'verification agronomic cohorts must match activation receipt';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_verification_agronomic_cohorts ON decision_model_post_activation_verifications;
CREATE TRIGGER trg_verification_agronomic_cohorts BEFORE INSERT ON decision_model_post_activation_verifications
FOR EACH ROW EXECUTE FUNCTION decision_assert_verification_cohorts();

CREATE OR REPLACE FUNCTION decision_assert_rollout_cohorts() RETURNS trigger AS $$
DECLARE src record;
BEGIN
  SELECT agronomic_cohorts, agronomic_cohort_fingerprint INTO src
  FROM decision_model_registry_activation_receipts
  WHERE tenant_id=NEW.tenant_id AND activation_receipt_id=NEW.activation_receipt_id;
  IF NOT FOUND OR NEW.agronomic_cohorts IS DISTINCT FROM src.agronomic_cohorts
     OR NEW.agronomic_cohort_fingerprint IS DISTINCT FROM src.agronomic_cohort_fingerprint THEN
    RAISE EXCEPTION 'rollout agronomic cohorts must match activation receipt';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_rollout_agronomic_cohorts ON decision_model_rollout_plans;
CREATE TRIGGER trg_rollout_agronomic_cohorts BEFORE INSERT ON decision_model_rollout_plans
FOR EACH ROW EXECUTE FUNCTION decision_assert_rollout_cohorts();

CREATE OR REPLACE FUNCTION decision_assert_monitoring_cohorts() RETURNS trigger AS $$
DECLARE src record;
BEGIN
  IF NEW.source_receipt_id IS NULL THEN RAISE EXCEPTION 'monitoring snapshot requires source_receipt_id'; END IF;
  SELECT c.model_id,c.feature_set_id,c.target_environment,r.agronomic_cohorts,r.agronomic_cohort_fingerprint INTO src
  FROM decision_model_registry_activation_receipts r
  JOIN decision_model_registry_activation_commands c USING(activation_command_id)
  WHERE r.tenant_id=NEW.tenant_id AND r.activation_receipt_id=NEW.source_receipt_id AND r.receipt_state='activated';
  IF NOT FOUND OR NEW.model_id IS DISTINCT FROM src.model_id OR NEW.feature_set_id IS DISTINCT FROM src.feature_set_id
     OR NEW.target_environment IS DISTINCT FROM src.target_environment
     OR NEW.agronomic_cohorts IS DISTINCT FROM src.agronomic_cohorts
     OR NEW.agronomic_cohort_fingerprint IS DISTINCT FROM src.agronomic_cohort_fingerprint THEN
    RAISE EXCEPTION 'monitoring snapshot must match active receipt and agronomic cohorts';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_monitoring_agronomic_cohorts ON decision_model_monitoring_snapshots;
CREATE TRIGGER trg_monitoring_agronomic_cohorts BEFORE INSERT ON decision_model_monitoring_snapshots
FOR EACH ROW EXECUTE FUNCTION decision_assert_monitoring_cohorts();

CREATE OR REPLACE FUNCTION decision_assert_retraining_cohorts() RETURNS trigger AS $$
DECLARE src record;
BEGIN
  IF NEW.source_monitoring_snapshot_id IS NULL THEN RAISE EXCEPTION 'retraining request requires source_monitoring_snapshot_id'; END IF;
  SELECT model_id,feature_set_id,target_environment,agronomic_cohorts,agronomic_cohort_fingerprint INTO src
  FROM decision_model_monitoring_snapshots
  WHERE tenant_id=NEW.tenant_id AND monitoring_snapshot_id=NEW.source_monitoring_snapshot_id;
  IF NOT FOUND OR NEW.model_id IS DISTINCT FROM src.model_id OR NEW.feature_set_id IS DISTINCT FROM src.feature_set_id
     OR NEW.target_environment IS DISTINCT FROM src.target_environment
     OR NEW.agronomic_cohorts IS DISTINCT FROM src.agronomic_cohorts
     OR NEW.agronomic_cohort_fingerprint IS DISTINCT FROM src.agronomic_cohort_fingerprint THEN
    RAISE EXCEPTION 'retraining request must inherit monitoring agronomic cohorts';
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_retraining_agronomic_cohorts ON decision_model_retraining_requests;
CREATE TRIGGER trg_retraining_agronomic_cohorts BEFORE INSERT ON decision_model_retraining_requests
FOR EACH ROW EXECUTE FUNCTION decision_assert_retraining_cohorts();

CREATE INDEX IF NOT EXISTS idx_monitoring_agronomic_cohort ON decision_model_monitoring_snapshots
(tenant_id, agronomic_cohort_fingerprint, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_retraining_agronomic_cohort ON decision_model_retraining_requests
(tenant_id, agronomic_cohort_fingerprint, requested_at DESC);
