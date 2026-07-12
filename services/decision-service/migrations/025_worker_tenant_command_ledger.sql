-- Forensic hardening (F-02/F-06/F-07 of the 73666ee audit): worker→tenant authorization
-- becomes an IMMUTABLE COMMAND LEDGER + a derived current projection.
--
-- Why: the previous single-row upsert overwrote idempotency_key on every change, so a
-- DELAYED RETRY of an old "enable" command could resurrect a tenant an operator had
-- since revoked (stale-idempotency replay). Replays are now resolved against the
-- append-only ledger: an old command returns its ORIGINAL outcome without touching the
-- current projection — retries are monotonic and revocation is final.
CREATE TABLE IF NOT EXISTS decision_runtime_worker_tenant_commands (
 command_id text PRIMARY KEY,
 worker_id text NOT NULL,
 tenant_id uuid NOT NULL,
 requested_enabled boolean NOT NULL,
 created_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 idempotency_key text NOT NULL,
 request_hash text NOT NULL,
 resulting_revision integer NOT NULL,
 UNIQUE(worker_id, idempotency_key),
 CHECK (length(btrim(worker_id)) BETWEEN 1 AND 128),
 CHECK (length(btrim(created_by)) BETWEEN 1 AND 256),
 CHECK (length(btrim(idempotency_key)) BETWEEN 1 AND 256),
 CHECK (request_hash ~ '^[0-9a-f]{64}$')
);
CREATE INDEX IF NOT EXISTS idx_worker_tenant_commands_pair
  ON decision_runtime_worker_tenant_commands (worker_id, tenant_id, created_at DESC);

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname='decision_wx11_completion_append_only') THEN
    EXECUTE 'DROP TRIGGER IF EXISTS trg_worker_tenant_commands_append_only ON decision_runtime_worker_tenant_commands';
    EXECUTE 'CREATE TRIGGER trg_worker_tenant_commands_append_only BEFORE UPDATE OR DELETE ON decision_runtime_worker_tenant_commands FOR EACH ROW EXECUTE FUNCTION decision_wx11_completion_append_only()';
  END IF;
END $$;

-- The mapping table stays as the CURRENT PROJECTION, now with a monotonic revision so
-- concurrent updates resolve deterministically and audits can order state changes.
ALTER TABLE decision_runtime_worker_tenants
  ADD COLUMN IF NOT EXISTS revision integer NOT NULL DEFAULT 1;

-- F-07: identifier/hash sanity on the projection too (NOT VALID: existing rows untouched,
-- every new write validated).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_worker_tenants_worker_id') THEN
    ALTER TABLE decision_runtime_worker_tenants
      ADD CONSTRAINT ck_worker_tenants_worker_id
      CHECK (length(btrim(worker_id)) BETWEEN 1 AND 128) NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_worker_tenants_created_by') THEN
    ALTER TABLE decision_runtime_worker_tenants
      ADD CONSTRAINT ck_worker_tenants_created_by
      CHECK (length(btrim(created_by)) BETWEEN 1 AND 256) NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_worker_tenants_request_hash') THEN
    ALTER TABLE decision_runtime_worker_tenants
      ADD CONSTRAINT ck_worker_tenants_request_hash
      CHECK (request_hash ~ '^[0-9a-f]{64}$') NOT VALID;
  END IF;
END $$;
