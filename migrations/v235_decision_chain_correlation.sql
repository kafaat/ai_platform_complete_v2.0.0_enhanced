ALTER TABLE decision_record ADD COLUMN IF NOT EXISTS correlation_id uuid;
CREATE INDEX IF NOT EXISTS idx_decision_record_correlation
  ON decision_record (tenant_id, correlation_id) WHERE correlation_id IS NOT NULL;
COMMENT ON COLUMN decision_record.correlation_id IS
  'Server-owned opaque trace identity; NULL means historical or unbound. Not an authorization or evidence digest.';

ALTER TABLE dispatch_decisions ADD COLUMN IF NOT EXISTS correlation_id uuid;
CREATE INDEX IF NOT EXISTS idx_dispatch_decisions_correlation
  ON dispatch_decisions (tenant_id, correlation_id) WHERE correlation_id IS NOT NULL;
COMMENT ON COLUMN dispatch_decisions.correlation_id IS
  'Server-owned opaque trace identity; NULL means historical or unbound. Not an authorization or evidence digest.';

ALTER TABLE execution_ledger ADD COLUMN IF NOT EXISTS correlation_id uuid;
CREATE INDEX IF NOT EXISTS idx_execution_ledger_correlation
  ON execution_ledger (tenant_id, correlation_id) WHERE correlation_id IS NOT NULL;
COMMENT ON COLUMN execution_ledger.correlation_id IS
  'Server-owned opaque trace identity; NULL means historical or unbound. Not an authorization or evidence digest.';

ALTER TABLE as_applied_irrigation_runs ADD COLUMN IF NOT EXISTS correlation_id uuid;
CREATE INDEX IF NOT EXISTS idx_as_applied_irrigation_runs_correlation
  ON as_applied_irrigation_runs (tenant_id, correlation_id) WHERE correlation_id IS NOT NULL;
COMMENT ON COLUMN as_applied_irrigation_runs.correlation_id IS
  'Server-owned opaque trace identity; NULL means historical or unbound. Not an authorization or evidence digest.';

ALTER TABLE as_applied_irrigation_receipts ADD COLUMN IF NOT EXISTS correlation_id uuid;
CREATE INDEX IF NOT EXISTS idx_as_applied_irrigation_receipts_correlation
  ON as_applied_irrigation_receipts (tenant_id, correlation_id) WHERE correlation_id IS NOT NULL;
COMMENT ON COLUMN as_applied_irrigation_receipts.correlation_id IS
  'Server-owned opaque trace identity; NULL means historical or unbound. Not an authorization or evidence digest.';
-- Additive tracing only. Existing rows remain NULL; no audit digest or data backfill.
-- SECURITY INVOKER is deliberate: parent reads keep the caller's RLS boundary.
CREATE OR REPLACE FUNCTION sahool_chain_correlation_root()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
BEGIN
  IF NEW.correlation_id IS NOT NULL THEN
    RAISE EXCEPTION 'root correlation is server-owned' USING ERRCODE = 'check_violation';
  END IF;
  NEW.correlation_id := gen_random_uuid();
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION sahool_chain_correlation_immutable()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
DECLARE identity_key text;
BEGIN
  IF NEW.correlation_id IS DISTINCT FROM OLD.correlation_id
     OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
    RAISE EXCEPTION 'correlation identity is immutable' USING ERRCODE = 'check_violation';
  END IF;
  FOREACH identity_key IN ARRAY TG_ARGV LOOP
    IF to_jsonb(NEW)->identity_key IS DISTINCT FROM to_jsonb(OLD)->identity_key THEN
      RAISE EXCEPTION 'correlation parent identity is immutable' USING ERRCODE = 'check_violation';
    END IF;
  END LOOP;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION sahool_platform_chain_correlation()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
DECLARE parent_correlation uuid;
BEGIN
  CASE TG_TABLE_NAME
    WHEN 'execution_ledger' THEN
      -- This decision_id is a dispatch identity, not an agronomic decision identity.
      SELECT correlation_id INTO parent_correlation FROM public.dispatch_decisions
       WHERE tenant_id=NEW.tenant_id AND decision_id=NEW.decision_id;
    WHEN 'as_applied_irrigation_runs' THEN
      SELECT correlation_id INTO parent_correlation FROM public.decision_record
       WHERE tenant_id=NEW.tenant_id AND decision_id=NEW.decision_id;
    WHEN 'as_applied_irrigation_receipts' THEN
      SELECT correlation_id INTO parent_correlation FROM public.as_applied_irrigation_runs
       WHERE tenant_id=NEW.tenant_id AND id=NEW.run_id;
    ELSE RAISE EXCEPTION 'unsupported correlation table' USING ERRCODE='check_violation';
  END CASE;
  IF NOT FOUND THEN
    -- v68 and v178 do not require a decision parent: preserve their existing
    -- unbound-write contract. Never manufacture a trace or probe another tenant.
    IF NEW.correlation_id IS NOT NULL THEN
      RAISE EXCEPTION 'correlation requires a visible same-tenant parent' USING ERRCODE='check_violation';
    END IF;
    NEW.correlation_id := NULL;
    RETURN NEW;
  END IF;
  IF NEW.correlation_id IS NOT NULL AND NEW.correlation_id IS DISTINCT FROM parent_correlation THEN
    RAISE EXCEPTION 'correlation conflicts with parent' USING ERRCODE='check_violation';
  END IF;
  NEW.correlation_id := parent_correlation;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_decision_record_correlation_insert ON decision_record;
CREATE TRIGGER trg_decision_record_correlation_insert BEFORE INSERT ON decision_record
  FOR EACH ROW EXECUTE FUNCTION sahool_chain_correlation_root();
DROP TRIGGER IF EXISTS trg_decision_record_correlation_immutable ON decision_record;
CREATE TRIGGER trg_decision_record_correlation_immutable BEFORE UPDATE ON decision_record
  FOR EACH ROW EXECUTE FUNCTION sahool_chain_correlation_immutable('decision_id');
DROP TRIGGER IF EXISTS trg_dispatch_decisions_correlation_insert ON dispatch_decisions;
CREATE TRIGGER trg_dispatch_decisions_correlation_insert BEFORE INSERT ON dispatch_decisions
  FOR EACH ROW EXECUTE FUNCTION sahool_chain_correlation_root();
DROP TRIGGER IF EXISTS trg_dispatch_decisions_correlation_immutable ON dispatch_decisions;
CREATE TRIGGER trg_dispatch_decisions_correlation_immutable BEFORE UPDATE ON dispatch_decisions
  FOR EACH ROW EXECUTE FUNCTION sahool_chain_correlation_immutable('decision_id');
DROP TRIGGER IF EXISTS trg_execution_ledger_correlation_insert ON execution_ledger;
CREATE TRIGGER trg_execution_ledger_correlation_insert BEFORE INSERT ON execution_ledger
  FOR EACH ROW EXECUTE FUNCTION sahool_platform_chain_correlation();
DROP TRIGGER IF EXISTS trg_execution_ledger_correlation_immutable ON execution_ledger;
CREATE TRIGGER trg_execution_ledger_correlation_immutable BEFORE UPDATE ON execution_ledger
  FOR EACH ROW EXECUTE FUNCTION sahool_chain_correlation_immutable('ledger_id','decision_id');
DROP TRIGGER IF EXISTS trg_as_applied_irrigation_runs_correlation_insert ON as_applied_irrigation_runs;
CREATE TRIGGER trg_as_applied_irrigation_runs_correlation_insert BEFORE INSERT ON as_applied_irrigation_runs
  FOR EACH ROW EXECUTE FUNCTION sahool_platform_chain_correlation();
DROP TRIGGER IF EXISTS trg_as_applied_irrigation_runs_correlation_immutable ON as_applied_irrigation_runs;
CREATE TRIGGER trg_as_applied_irrigation_runs_correlation_immutable BEFORE UPDATE ON as_applied_irrigation_runs
  FOR EACH ROW EXECUTE FUNCTION sahool_chain_correlation_immutable('id','decision_id','authorization_id','execution_plan_id');
DROP TRIGGER IF EXISTS trg_as_applied_irrigation_receipts_correlation_insert ON as_applied_irrigation_receipts;
CREATE TRIGGER trg_as_applied_irrigation_receipts_correlation_insert BEFORE INSERT ON as_applied_irrigation_receipts
  FOR EACH ROW EXECUTE FUNCTION sahool_platform_chain_correlation();
DROP TRIGGER IF EXISTS trg_as_applied_irrigation_receipts_correlation_immutable ON as_applied_irrigation_receipts;
CREATE TRIGGER trg_as_applied_irrigation_receipts_correlation_immutable BEFORE UPDATE ON as_applied_irrigation_receipts
  FOR EACH ROW EXECUTE FUNCTION sahool_chain_correlation_immutable('id','run_id');
