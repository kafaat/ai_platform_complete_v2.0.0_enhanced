-- 033's permissive policies can be OR-combined with older tenant_isolation
-- policies. The live v122 policy accepts app.tenant_id when the canonical
-- app.current_tenant is absent. Add an AND guard without changing 033's checksum
-- or deleting policies owned by the platform migration history.
-- Keep 033's permissive policy: PostgreSQL requires at least one permissive
-- policy to grant access before restrictive policies can narrow that access.

DROP POLICY IF EXISTS decision_outbox_events_tenant_boundary_guard ON decision_outbox_events;
CREATE POLICY decision_outbox_events_tenant_boundary_guard
  ON decision_outbox_events AS RESTRICTIVE
  FOR ALL
  USING (
    tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
  )
  WITH CHECK (
    tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
  );

DROP POLICY IF EXISTS decision_reviews_tenant_boundary_guard ON decision_reviews;
CREATE POLICY decision_reviews_tenant_boundary_guard
  ON decision_reviews AS RESTRICTIVE
  FOR ALL
  USING (
    tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
  )
  WITH CHECK (
    tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
  );
