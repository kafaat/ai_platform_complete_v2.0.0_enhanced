-- P4 governed soil execution, verification, outcome and learning lineage
CREATE TABLE IF NOT EXISTS soil_execution_records (
 execution_id text PRIMARY KEY, tenant_id text NOT NULL, field_id text NOT NULL, decision_id text NOT NULL,
 action_type text NOT NULL, profile_hash text NOT NULL, payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_soil_execution_decision ON soil_execution_records(tenant_id,decision_id);
CREATE TABLE IF NOT EXISTS soil_verification_records (
 verification_id text PRIMARY KEY, tenant_id text NOT NULL, field_id text NOT NULL, execution_id text NOT NULL REFERENCES soil_execution_records(execution_id), payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS soil_outcome_records (
 outcome_id text PRIMARY KEY, tenant_id text NOT NULL, field_id text NOT NULL, execution_id text NOT NULL REFERENCES soil_execution_records(execution_id), verification_id text, payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS soil_learning_attributions (
 learning_id text PRIMARY KEY, tenant_id text NOT NULL, field_id text NOT NULL, outcome_id text NOT NULL REFERENCES soil_outcome_records(outcome_id), execution_id text NOT NULL, profile_hash text NOT NULL, eligible_for_training boolean NOT NULL DEFAULT false, payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['soil_execution_records','soil_verification_records','soil_outcome_records','soil_learning_attributions'] LOOP
 EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t); EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I',t);
 EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.current_tenant'', true)) WITH CHECK (tenant_id = current_setting(''app.current_tenant'', true))',t);
END LOOP; END $$;
