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

ALTER TABLE decision_reviews ADD COLUMN IF NOT EXISTS correlation_id uuid;
CREATE INDEX IF NOT EXISTS idx_decision_reviews_correlation
  ON decision_reviews (tenant_id, correlation_id) WHERE correlation_id IS NOT NULL;
COMMENT ON COLUMN decision_reviews.correlation_id IS
  'Server-owned opaque trace identity; NULL means historical or unbound. Not an authorization or evidence digest.';

ALTER TABLE decision_execution_plans ADD COLUMN IF NOT EXISTS correlation_id uuid;
CREATE INDEX IF NOT EXISTS idx_decision_execution_plans_correlation
  ON decision_execution_plans (tenant_id, correlation_id) WHERE correlation_id IS NOT NULL;
COMMENT ON COLUMN decision_execution_plans.correlation_id IS
  'Server-owned opaque trace identity; NULL means historical or unbound. Not an authorization or evidence digest.';

ALTER TABLE decision_dispatch_authorizations ADD COLUMN IF NOT EXISTS correlation_id uuid;
CREATE INDEX IF NOT EXISTS idx_decision_dispatch_authorizations_correlation
  ON decision_dispatch_authorizations (tenant_id, correlation_id) WHERE correlation_id IS NOT NULL;
COMMENT ON COLUMN decision_dispatch_authorizations.correlation_id IS
  'Server-owned opaque trace identity; NULL means historical or unbound. Not an authorization or evidence digest.';

ALTER TABLE decision_execution_requests ADD COLUMN IF NOT EXISTS correlation_id uuid;
CREATE INDEX IF NOT EXISTS idx_decision_execution_requests_correlation
  ON decision_execution_requests (tenant_id, correlation_id) WHERE correlation_id IS NOT NULL;
COMMENT ON COLUMN decision_execution_requests.correlation_id IS
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

CREATE OR REPLACE FUNCTION sahool_decision_chain_correlation()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
DECLARE parent_correlation uuid;
BEGIN
  CASE TG_TABLE_NAME
    WHEN 'decision_reviews' THEN
      SELECT d.correlation_id INTO parent_correlation FROM public.decision_record d
       WHERE d.tenant_id=NEW.tenant_id AND d.decision_id=NEW.decision_id;
    WHEN 'decision_execution_plans' THEN
      SELECT r.correlation_id INTO parent_correlation FROM public.decision_reviews r
       WHERE r.tenant_id=NEW.tenant_id AND r.review_id=NEW.review_id AND r.decision_id=NEW.decision_id;
    WHEN 'decision_dispatch_authorizations' THEN
      SELECT p.correlation_id INTO parent_correlation FROM public.decision_execution_plans p
       WHERE p.tenant_id=NEW.tenant_id AND p.execution_plan_id=NEW.execution_plan_id
         AND p.decision_id=NEW.decision_id AND p.review_id=NEW.review_id;
    WHEN 'decision_execution_requests' THEN
      SELECT a.correlation_id INTO parent_correlation FROM public.decision_dispatch_authorizations a
       WHERE a.tenant_id=NEW.tenant_id AND a.dispatch_authorization_id=NEW.dispatch_authorization_id
         AND a.decision_id=NEW.decision_id AND a.execution_plan_id=NEW.execution_plan_id;
    ELSE RAISE EXCEPTION 'unsupported correlation table' USING ERRCODE='check_violation';
  END CASE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'same-tenant correlation parent unavailable' USING ERRCODE='foreign_key_violation';
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
DROP TRIGGER IF EXISTS trg_decision_reviews_correlation_insert ON decision_reviews;
CREATE TRIGGER trg_decision_reviews_correlation_insert BEFORE INSERT ON decision_reviews
  FOR EACH ROW EXECUTE FUNCTION sahool_decision_chain_correlation();
DROP TRIGGER IF EXISTS trg_decision_reviews_correlation_immutable ON decision_reviews;
CREATE TRIGGER trg_decision_reviews_correlation_immutable BEFORE UPDATE ON decision_reviews
  FOR EACH ROW EXECUTE FUNCTION sahool_chain_correlation_immutable('review_id','decision_id');
DROP TRIGGER IF EXISTS trg_decision_execution_plans_correlation_insert ON decision_execution_plans;
CREATE TRIGGER trg_decision_execution_plans_correlation_insert BEFORE INSERT ON decision_execution_plans
  FOR EACH ROW EXECUTE FUNCTION sahool_decision_chain_correlation();
DROP TRIGGER IF EXISTS trg_decision_execution_plans_correlation_immutable ON decision_execution_plans;
CREATE TRIGGER trg_decision_execution_plans_correlation_immutable BEFORE UPDATE ON decision_execution_plans
  FOR EACH ROW EXECUTE FUNCTION sahool_chain_correlation_immutable('execution_plan_id','review_id','decision_id');
DROP TRIGGER IF EXISTS trg_decision_dispatch_authorizations_correlation_insert ON decision_dispatch_authorizations;
CREATE TRIGGER trg_decision_dispatch_authorizations_correlation_insert BEFORE INSERT ON decision_dispatch_authorizations
  FOR EACH ROW EXECUTE FUNCTION sahool_decision_chain_correlation();
DROP TRIGGER IF EXISTS trg_decision_dispatch_authorizations_correlation_immutable ON decision_dispatch_authorizations;
CREATE TRIGGER trg_decision_dispatch_authorizations_correlation_immutable BEFORE UPDATE ON decision_dispatch_authorizations
  FOR EACH ROW EXECUTE FUNCTION sahool_chain_correlation_immutable('dispatch_authorization_id','execution_plan_id','review_id','decision_id');
DROP TRIGGER IF EXISTS trg_decision_execution_requests_correlation_insert ON decision_execution_requests;
CREATE TRIGGER trg_decision_execution_requests_correlation_insert BEFORE INSERT ON decision_execution_requests
  FOR EACH ROW EXECUTE FUNCTION sahool_decision_chain_correlation();
DROP TRIGGER IF EXISTS trg_decision_execution_requests_correlation_immutable ON decision_execution_requests;
CREATE TRIGGER trg_decision_execution_requests_correlation_immutable BEFORE UPDATE ON decision_execution_requests
  FOR EACH ROW EXECUTE FUNCTION sahool_chain_correlation_immutable('execution_request_id','dispatch_authorization_id','execution_plan_id','decision_id');
