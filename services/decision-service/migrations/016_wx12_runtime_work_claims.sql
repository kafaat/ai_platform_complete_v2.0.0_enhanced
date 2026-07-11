-- WX-12.2 durable runtime-work claims: multi-replica safety for the side-effecting work types
-- (post-activation verification, rollout application, retraining dispatch) which — unlike
-- activation/rollback — had no claim table. A claim is a lease (owner + expiry + attempt); the
-- work-feed hands each side-effecting item to at most one live-leased worker, and an expired
-- lease is reclaimable (attempt incremented). This is a mutable lease ledger, NOT append-only.
CREATE TABLE IF NOT EXISTS decision_model_runtime_work_claims (
 work_claim_id text PRIMARY KEY, tenant_id uuid NOT NULL,
 work_type text NOT NULL, work_key text NOT NULL, worker_id text NOT NULL,
 lease_expires_at timestamptz NOT NULL, attempt integer NOT NULL DEFAULT 1,
 claimed_at timestamptz NOT NULL DEFAULT now(), heartbeat_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant_id, work_type, work_key),
 CHECK (work_type IN ('post_activation_verification','rollout_apply','retraining_dispatch'))
);
CREATE INDEX IF NOT EXISTS idx_runtime_work_claims_lease
  ON decision_model_runtime_work_claims (tenant_id, work_type, lease_expires_at);
