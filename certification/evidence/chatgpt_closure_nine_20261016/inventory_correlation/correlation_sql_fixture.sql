-- Minimal relational projection used only for trigger-contract tests, not a migration-chain proof.
CREATE TABLE decision_record (decision_id text PRIMARY KEY, tenant_id uuid NOT NULL, decision_value jsonb DEFAULT '{}', content_digest text);
CREATE TABLE dispatch_decisions (decision_id text PRIMARY KEY, tenant_id uuid NOT NULL);
CREATE TABLE execution_ledger (ledger_id text PRIMARY KEY, tenant_id uuid NOT NULL, decision_id text, content_hash text);
CREATE TABLE as_applied_irrigation_runs (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, decision_id text, authorization_id text, execution_plan_id text);
CREATE TABLE as_applied_irrigation_receipts (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, run_id uuid, receipt_digest text);
CREATE TABLE decision_reviews (review_id text PRIMARY KEY, tenant_id uuid NOT NULL, decision_id text);
CREATE TABLE decision_execution_plans (execution_plan_id text PRIMARY KEY, tenant_id uuid NOT NULL, decision_id text, review_id text);
CREATE TABLE decision_dispatch_authorizations (dispatch_authorization_id text PRIMARY KEY, tenant_id uuid NOT NULL, decision_id text, review_id text, execution_plan_id text);
CREATE TABLE decision_execution_requests (execution_request_id text PRIMARY KEY, tenant_id uuid NOT NULL, decision_id text, execution_plan_id text, dispatch_authorization_id text, status text);
INSERT INTO decision_record(decision_id,tenant_id) VALUES ('legacy','00000000-0000-4000-8000-000000000001');
CREATE ROLE correlation_probe NOSUPERUSER NOBYPASSRLS;
DO $$ DECLARE t text; BEGIN
 FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (tenant_id::text = NULLIF(current_setting(''app.current_tenant'',true),'''')) WITH CHECK (tenant_id::text = NULLIF(current_setting(''app.current_tenant'',true),''''))',t);
  EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON %I TO correlation_probe',t);
 END LOOP;
END $$;
