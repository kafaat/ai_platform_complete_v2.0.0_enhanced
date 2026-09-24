-- Decision SoR tenant-boundary hardening.
-- Live staging counterexample (2026-09-24) proved decision_outbox_events allowed
-- cross-tenant reads/writes under the restricted sahool_app role.
--
-- Scope is deliberately narrow: only tables whose request/write paths already bind
-- app.current_tenant transaction-locally are hardened here. Do not mechanically apply
-- this policy to worker/claim/model-runtime tables until their consumer identity model
-- has been audited.

ALTER TABLE decision_outbox_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_outbox_events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS decision_outbox_events_tenant_isolation ON decision_outbox_events;
CREATE POLICY decision_outbox_events_tenant_isolation
  ON decision_outbox_events
  FOR ALL
  USING (
    tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
  )
  WITH CHECK (
    tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
  );

ALTER TABLE decision_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_reviews FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS decision_reviews_tenant_isolation ON decision_reviews;
CREATE POLICY decision_reviews_tenant_isolation
  ON decision_reviews
  FOR ALL
  USING (
    tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
  )
  WITH CHECK (
    tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
  );
