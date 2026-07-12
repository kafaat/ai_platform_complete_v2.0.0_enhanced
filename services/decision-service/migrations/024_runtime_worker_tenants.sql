-- WX-12 multi-tenancy: server-authorized worker→tenant partitioning.
-- A runtime worker may only pull work for tenants an operator registered for it — the
-- worker can no longer free-pick tenants via the X-Tenant-Id header once registered.
-- Compatibility: a worker with NO registrations keeps the legacy single-tenant behavior
-- (its deployment still pins the tenant via env), so existing installs are not bricked;
-- registering the first row flips the worker into enforced partitioning.
--
-- NOTE (by design): this is a cross-tenant OPERATOR configuration table — the
-- authorization map itself — so it carries no tenant RLS. It is mutable (enable/disable
-- a registration) but every change is stamped (created_by / updated_at) and idempotent.
CREATE TABLE IF NOT EXISTS decision_runtime_worker_tenants (
 registration_id text PRIMARY KEY,
 worker_id text NOT NULL,
 tenant_id uuid NOT NULL,
 enabled boolean NOT NULL DEFAULT true,
 created_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL,
 request_hash text NOT NULL,
 UNIQUE(worker_id, tenant_id),
 UNIQUE(worker_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_runtime_worker_tenants_enabled
  ON decision_runtime_worker_tenants (worker_id) WHERE enabled;
