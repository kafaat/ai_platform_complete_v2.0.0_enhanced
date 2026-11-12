-- Decision SoR: FORCE tenant RLS on every remaining decision table with tenant_id.
--
-- Why
-- ---
-- The decision-service tables live in the same PostgreSQL database as the platform.
-- Platform migration migrations/v206_rls_final_hardening.sql (which must stay last in
-- migrations/MANIFEST.txt) asserts that EVERY public table carrying a tenant_id column
-- has ROW LEVEL SECURITY enabled AND forced AND at least one ALL/INSERT/UPDATE policy
-- with a non-null WITH CHECK. Once 001..036 had run, 32 decision tables violated that
-- assertion ("v206 catalog assertion"), so every deploy that re-applies the platform
-- MANIFEST aborted at v206.
--
-- 033 deliberately hardened only tables whose code paths already bound
-- app.current_tenant, and deferred worker/claim/model-runtime tables "until their
-- consumer identity model has been audited". That audit is now done:
--   * The runtime role owns these tables (migrations run under the same DATABASE_URL),
--     so without FORCE the owner silently bypasses RLS; FORCE makes the policies apply
--     to it too.
--   * tenant_id is uuid NOT NULL on all of them, so the policy has no NULL escape.
--   * Every tenant-scoped read/write in persistence.py now binds app.current_tenant
--     transaction-locally before its first statement (the previously unbound reads -
--     context snapshot, agronomic evidence, calibration dataset, queued/in-flight
--     execution feeds, active model state, runtime work feed + leases, reservation
--     inbox - were fixed together with this migration).
--   * Two tables are NOT tenant-partitioned by their consumers but worker-partitioned:
--     decision_runtime_worker_tenants and decision_runtime_worker_tenant_commands. Their
--     lookups are by worker_id across tenants (tenant discovery, the "is this worker
--     registered at all" probe, and the (worker_id, idempotency_key) replay lookup that
--     is unique across tenants). A tenant-only policy would make the registration probe
--     return nothing for a registered worker, which the service treats as "unregistered"
--     and, in legacy mode, ALLOWS any tenant (fail-open). They get a worker-aware policy.
--
-- Idempotent: ALTER TABLE ... ENABLE/FORCE are no-ops when already set, and every policy
-- is DROP POLICY IF EXISTS + CREATE POLICY. Policy names are table-prefixed (as in 033)
-- so they never collide with the platform's generic "tenant_isolation" policies that
-- v206 step (1) rewrites.

-- (A) RLS and a fail-closed tenant policy already exist (019, 020); only FORCE was
--     missing, so the owning runtime role bypassed them.
ALTER TABLE decision_agronomic_context_snapshots FORCE ROW LEVEL SECURITY;
ALTER TABLE decision_feature_manifest_entries FORCE ROW LEVEL SECURITY;
ALTER TABLE decision_feature_manifests FORCE ROW LEVEL SECURITY;
ALTER TABLE decision_field_historical_context_snapshots FORCE ROW LEVEL SECURITY;
ALTER TABLE decision_vegetation_snapshots FORCE ROW LEVEL SECURITY;
ALTER TABLE decision_learning_attributions FORCE ROW LEVEL SECURITY;

-- (B) No RLS before this migration. Same fail-closed predicate as 033: with no
--     app.current_tenant the NULLIF yields NULL, the comparison is never true, and the
--     row is neither visible nor writable.
ALTER TABLE decision_dispatch_authorizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_dispatch_authorizations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_dispatch_authorizations_tenant_isolation ON decision_dispatch_authorizations;
CREATE POLICY decision_dispatch_authorizations_tenant_isolation
  ON decision_dispatch_authorizations
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_execution_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_execution_plans FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_execution_plans_tenant_isolation ON decision_execution_plans;
CREATE POLICY decision_execution_plans_tenant_isolation
  ON decision_execution_plans
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_execution_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_execution_requests FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_execution_requests_tenant_isolation ON decision_execution_requests;
CREATE POLICY decision_execution_requests_tenant_isolation
  ON decision_execution_requests
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_execution_delivery_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_execution_delivery_attempts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_execution_delivery_attempts_tenant_isolation ON decision_execution_delivery_attempts;
CREATE POLICY decision_execution_delivery_attempts_tenant_isolation
  ON decision_execution_delivery_attempts
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_evaluation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_evaluation_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_evaluation_runs_tenant_isolation ON decision_model_evaluation_runs;
CREATE POLICY decision_model_evaluation_runs_tenant_isolation
  ON decision_model_evaluation_runs
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_promotion_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_promotion_decisions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_promotion_decisions_tenant_isolation ON decision_model_promotion_decisions;
CREATE POLICY decision_model_promotion_decisions_tenant_isolation
  ON decision_model_promotion_decisions
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_activation_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_activation_requests FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_activation_requests_tenant_isolation ON decision_model_activation_requests;
CREATE POLICY decision_model_activation_requests_tenant_isolation
  ON decision_model_activation_requests
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_activation_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_activation_reviews FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_activation_reviews_tenant_isolation ON decision_model_activation_reviews;
CREATE POLICY decision_model_activation_reviews_tenant_isolation
  ON decision_model_activation_reviews
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_registry_activation_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_registry_activation_claims FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_registry_activation_claims_tenant_isolation ON decision_model_registry_activation_claims;
CREATE POLICY decision_model_registry_activation_claims_tenant_isolation
  ON decision_model_registry_activation_claims
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_registry_rollback_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_registry_rollback_claims FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_registry_rollback_claims_tenant_isolation ON decision_model_registry_rollback_claims;
CREATE POLICY decision_model_registry_rollback_claims_tenant_isolation
  ON decision_model_registry_rollback_claims
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_registry_activation_commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_registry_activation_commands FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_registry_activation_commands_tenant_isolation ON decision_model_registry_activation_commands;
CREATE POLICY decision_model_registry_activation_commands_tenant_isolation
  ON decision_model_registry_activation_commands
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_registry_activation_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_registry_activation_receipts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_registry_activation_receipts_tenant_isolation ON decision_model_registry_activation_receipts;
CREATE POLICY decision_model_registry_activation_receipts_tenant_isolation
  ON decision_model_registry_activation_receipts
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_registry_rollback_commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_registry_rollback_commands FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_registry_rollback_commands_tenant_isolation ON decision_model_registry_rollback_commands;
CREATE POLICY decision_model_registry_rollback_commands_tenant_isolation
  ON decision_model_registry_rollback_commands
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_registry_rollback_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_registry_rollback_receipts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_registry_rollback_receipts_tenant_isolation ON decision_model_registry_rollback_receipts;
CREATE POLICY decision_model_registry_rollback_receipts_tenant_isolation
  ON decision_model_registry_rollback_receipts
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_post_activation_verifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_post_activation_verifications FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_post_activation_verifications_tenant_isolation ON decision_model_post_activation_verifications;
CREATE POLICY decision_model_post_activation_verifications_tenant_isolation
  ON decision_model_post_activation_verifications
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_rollout_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_rollout_plans FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_rollout_plans_tenant_isolation ON decision_model_rollout_plans;
CREATE POLICY decision_model_rollout_plans_tenant_isolation
  ON decision_model_rollout_plans
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_rollout_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_rollout_receipts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_rollout_receipts_tenant_isolation ON decision_model_rollout_receipts;
CREATE POLICY decision_model_rollout_receipts_tenant_isolation
  ON decision_model_rollout_receipts
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_monitoring_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_monitoring_snapshots FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_monitoring_snapshots_tenant_isolation ON decision_model_monitoring_snapshots;
CREATE POLICY decision_model_monitoring_snapshots_tenant_isolation
  ON decision_model_monitoring_snapshots
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_retraining_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_retraining_requests FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_retraining_requests_tenant_isolation ON decision_model_retraining_requests;
CREATE POLICY decision_model_retraining_requests_tenant_isolation
  ON decision_model_retraining_requests
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_retraining_dispatch_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_retraining_dispatch_receipts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_retraining_dispatch_receipts_tenant_isolation ON decision_model_retraining_dispatch_receipts;
CREATE POLICY decision_model_retraining_dispatch_receipts_tenant_isolation
  ON decision_model_retraining_dispatch_receipts
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_runtime_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_runtime_schedules FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_runtime_schedules_tenant_isolation ON decision_model_runtime_schedules;
CREATE POLICY decision_model_runtime_schedules_tenant_isolation
  ON decision_model_runtime_schedules
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_reconcile_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_reconcile_evidence FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_reconcile_evidence_tenant_isolation ON decision_model_reconcile_evidence;
CREATE POLICY decision_model_reconcile_evidence_tenant_isolation
  ON decision_model_reconcile_evidence
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_model_runtime_work_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_model_runtime_work_claims FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_model_runtime_work_claims_tenant_isolation ON decision_model_runtime_work_claims;
CREATE POLICY decision_model_runtime_work_claims_tenant_isolation
  ON decision_model_runtime_work_claims
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

ALTER TABLE decision_reservation_dispatch_inbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_reservation_dispatch_inbox FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_reservation_dispatch_inbox_tenant_isolation ON decision_reservation_dispatch_inbox;
CREATE POLICY decision_reservation_dispatch_inbox_tenant_isolation
  ON decision_reservation_dispatch_inbox
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

-- (C) Worker-partitioned tables.
--
-- Read side (SELECT): a row is visible when it belongs to the bound tenant OR to the
-- bound worker. The service sets app.current_worker transaction-locally only after it
-- has authenticated the caller as that worker (WORKER-IDENTITY-BINDING) or as the
-- operator administering that worker's registrations. With neither setting bound
-- nothing is visible (fail-closed).
--
-- What this does and does NOT protect against, stated precisely: app.current_worker is
-- a custom GUC, so ANY session of the runtime role can set it to any value - exactly as
-- any session of that role can already set app.current_tenant to any tenant. The
-- database does not authenticate either setting; both are trusted only because the
-- service code sets them after its own authentication. The worker setting therefore
-- adds no capability beyond what the tenant setting already grants to that role:
--   * it grants nothing on writes (see below);
--   * on reads it exposes one worker's registrations across tenants, which the same
--     session could equally read tenant by tenant under app.current_tenant. The only
--     difference is the key: a session that knows a worker_id (rather than tenant
--     uuids) learns the tenant uuids that worker is registered for.
--
-- Write side (INSERT/UPDATE/DELETE): tenant-bound only. The worker clause lives in a
-- separate FOR SELECT policy (narrower than one FOR ALL policy with an OR), so a worker
-- binding can neither create a row in any tenant (WITH CHECK) nor update/delete another
-- tenant's registration (USING of the FOR ALL policy). Registering or changing a
-- worker->tenant authorization always runs under that tenant's binding. Permissive
-- policies OR-combine per command, so SELECT gets tenant OR worker while every write
-- gets tenant only.
ALTER TABLE decision_runtime_worker_tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_runtime_worker_tenants FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_runtime_worker_tenants_tenant_isolation ON decision_runtime_worker_tenants;
CREATE POLICY decision_runtime_worker_tenants_tenant_isolation
  ON decision_runtime_worker_tenants
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
DROP POLICY IF EXISTS decision_runtime_worker_tenants_worker_read ON decision_runtime_worker_tenants;
CREATE POLICY decision_runtime_worker_tenants_worker_read
  ON decision_runtime_worker_tenants
  FOR SELECT
  USING (worker_id = NULLIF(current_setting('app.current_worker', true), ''));

ALTER TABLE decision_runtime_worker_tenant_commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_runtime_worker_tenant_commands FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decision_runtime_worker_tenant_commands_tenant_isolation ON decision_runtime_worker_tenant_commands;
CREATE POLICY decision_runtime_worker_tenant_commands_tenant_isolation
  ON decision_runtime_worker_tenant_commands
  FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
DROP POLICY IF EXISTS decision_runtime_worker_tenant_commands_worker_read ON decision_runtime_worker_tenant_commands;
CREATE POLICY decision_runtime_worker_tenant_commands_worker_read
  ON decision_runtime_worker_tenant_commands
  FOR SELECT
  USING (worker_id = NULLIF(current_setting('app.current_worker', true), ''));
