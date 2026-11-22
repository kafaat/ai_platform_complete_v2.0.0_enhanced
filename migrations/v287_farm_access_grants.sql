-- v287 (Service Center SC-1, owner decision C; number provisional until merge, SHR-02):
-- per-farm access grants and the farm-scope row-level policies that read them.
--
-- farm_access_grants.user_id is the JWT ``sub`` the platform puts in app.current_user_id, that
-- is the AUTH service's users.id as text. It is not the platform database's users.id: the two
-- are different identifiers when auth has its own database, so a grant keyed by the platform id
-- never matches a session (tests_v9/test_farm_access_scope_live_pg.py proves both directions).
--
-- Visibility is unchanged by this file. Every policy below is RESTRICTIVE and passes unless the
-- session sets app.enforce_farm_scope = 'on'. sahool-platform sets that GUC only when
-- SAHOOL_FARM_SCOPE_ENFORCE is on (default off) AND this file is applied (api/farm_scope.py);
-- no other service sets it. Turning it on is an owner decision taken after
-- scripts/ops/farm_access_diff.py reports no lost or newly permitted (user, tenant, farm, action).
--
-- Under enforcement:
--   * an owner (app.current_role = 'owner') keeps every farm of the tenant;
--   * any other role sees a farm only through an active grant for (tenant, sub, farm);
--   * fields, seasons and field_tasks follow their field's farm; a farm ledger entry follows its
--     farm and, when it names one, its field;
--   * a row with no farm (fields.farm_id is nullable) is not farm-scoped and stays visible to the
--     tenant, so full grants reproduce today's visibility exactly;
--   * writes are stricter than reads: WITH CHECK and a RESTRICTIVE FOR DELETE policy use
--     sc_farm_writable / sc_field_writable, so a non-owner inserts, updates and deletes only rows
--     of a granted farm and never a row with no farm. Otherwise nulling farm_id, or moving a
--     season/task onto a farm-less field, would publish a granted farm's row to every user of
--     the tenant (security review, finding 1), and a non-owner could delete farm-less rows it may
--     not even edit (delta review B). So under enforcement farm-less rows are READ-ONLY for
--     non-owners; only owners write or delete them. Legacy fields were left farm-less when
--     farm_id was added (v19_farms.sql), so assign their farms before enforcement is switched on.
--
-- Who writes farm_access_grants: only the migration owner (a superuser), through the operator
-- backfill (scripts/ops/farm_access_backfill.py --apply, which refuses any other role). This file
-- revokes INSERT/UPDATE/DELETE/TRUNCATE from every other role holding them on the table, and
-- migrations/apply_in_compose.sh / bootstrap_postgres.sh revoke them from the application and jobs
-- roles after their broad grants. The provenance label 'backfill:%' is reserved for that
-- operator by a trigger, because farm_access_diff.py trusts it (delta review A).
-- The tenant policies (tenant_isolation, v9/v122/v206) are untouched and still apply first.
--
-- Not covered here: documents and service-center tables (SC-2 migrations). Owner: sahool-platform.
BEGIN;
SET LOCAL lock_timeout = '15s';

CREATE TABLE IF NOT EXISTS farm_access_grants (
    tenant_id UUID NOT NULL,
    user_id TEXT NOT NULL CHECK (btrim(user_id) <> ''),
    farm_id VARCHAR(50) NOT NULL REFERENCES farms(farm_id) ON DELETE RESTRICT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    granted_by TEXT NOT NULL CHECK (btrim(granted_by) <> ''),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, user_id, farm_id)
);
COMMENT ON COLUMN farm_access_grants.user_id IS
    'JWT sub = the auth service users.id as text (owner decision C), never the platform users.id';
CREATE INDEX IF NOT EXISTS idx_farm_access_grants_farm ON farm_access_grants (tenant_id, farm_id);

-- Tenant isolation, fail-closed both ways (no tenant context: no row read, no row written).
ALTER TABLE farm_access_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE farm_access_grants FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS farm_access_grants_tenant ON farm_access_grants;
CREATE POLICY farm_access_grants_tenant ON farm_access_grants
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

-- A session reads its own grants; only an owner context reads the tenant's other grants or
-- writes any. Migrations and the backfill's operator role bypass RLS; the application role does not.
DROP POLICY IF EXISTS farm_grant_read ON farm_access_grants;
CREATE POLICY farm_grant_read ON farm_access_grants AS RESTRICTIVE FOR SELECT
    USING (user_id = current_setting('app.current_user_id', true)
           OR current_setting('app.current_role', true) = 'owner');
DROP POLICY IF EXISTS farm_grant_owner_insert ON farm_access_grants;
CREATE POLICY farm_grant_owner_insert ON farm_access_grants AS RESTRICTIVE FOR INSERT
    WITH CHECK (current_setting('app.current_role', true) = 'owner');
DROP POLICY IF EXISTS farm_grant_owner_update ON farm_access_grants;
CREATE POLICY farm_grant_owner_update ON farm_access_grants AS RESTRICTIVE FOR UPDATE
    USING (current_setting('app.current_role', true) = 'owner')
    WITH CHECK (current_setting('app.current_role', true) = 'owner');
DROP POLICY IF EXISTS farm_grant_owner_delete ON farm_access_grants;
CREATE POLICY farm_grant_owner_delete ON farm_access_grants AS RESTRICTIVE FOR DELETE
    USING (current_setting('app.current_role', true) = 'owner');

-- Provenance: 'backfill:%' is the label farm_access_diff.py trusts, so only the operator may write
-- it. Operator = the migration owner: session_user AND current_user are superusers (no GUC, which
-- any session can set). A role that may write the table for another reason still cannot claim it.
CREATE OR REPLACE FUNCTION farm_access_grant_provenance_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
  IF NEW.granted_by LIKE 'backfill:%' AND NOT (
       COALESCE((SELECT r.rolsuper FROM pg_roles r WHERE r.rolname = session_user), false)
       AND COALESCE((SELECT r.rolsuper FROM pg_roles r WHERE r.rolname = current_user), false))
  THEN
    RAISE EXCEPTION 'farm_access_grants: granted_by % is reserved for the operator backfill run as the migration owner', NEW.granted_by
      USING ERRCODE = '42501';
  END IF;
  RETURN NEW;
END
$$;
DROP TRIGGER IF EXISTS farm_access_grant_provenance ON farm_access_grants;
CREATE TRIGGER farm_access_grant_provenance BEFORE INSERT OR UPDATE ON farm_access_grants
    FOR EACH ROW EXECUTE FUNCTION farm_access_grant_provenance_guard();

-- Only the migration owner writes grants: revoke write from every other role holding it here
-- (default privileges hand DML on new tables to the application and jobs roles). Idempotent;
-- the migrator re-runs the same revoke after its broad grants.
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT DISTINCT a.grantee::regrole::text AS grantee
    FROM pg_class c, aclexplode(c.relacl) a
    WHERE c.oid = 'public.farm_access_grants'::regclass
      AND a.privilege_type IN ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')
      AND a.grantee <> 0 AND a.grantee <> c.relowner
      AND NOT COALESCE((SELECT x.rolsuper FROM pg_roles x WHERE x.oid = a.grantee), false)
  LOOP
    EXECUTE format('REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.farm_access_grants FROM %s',
                   r.grantee);
  END LOOP;
END $$;

-- Why PL/pgSQL, and why every policy tests the GUC itself first: PostgreSQL checks privileges on
-- every relation a query references when it starts, even in a CASE branch that is never taken,
-- and an SQL function is inlined into the policy. Written as one SQL expression these policies
-- made every reader of farms/fields/... need SELECT on farm_access_grants, so a narrow role such
-- as sahool_ingest (SELECT ON fields only) got "permission denied for table farm_access_grants"
-- with enforcement OFF (measured on PostgreSQL 16). Here the policy short-circuits on the GUC,
-- the functions are entered only under enforcement, and their lookups are planned only when
-- reached. SECURITY INVOKER on purpose: the lookups run under the caller's tenant policies (and
-- farm_grant_read: a session sees only its own grants).
CREATE OR REPLACE FUNCTION sc_farm_visible(target_farm TEXT) RETURNS BOOLEAN
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, public AS $$
BEGIN
  IF current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
     OR current_setting('app.current_role', true) = 'owner'
     OR target_farm IS NULL THEN
    RETURN true;
  END IF;
  RETURN EXISTS (
    SELECT 1 FROM public.farm_access_grants g
    WHERE g.tenant_id::text = current_setting('app.current_tenant', true)
      AND g.user_id = current_setting('app.current_user_id', true)
      AND g.farm_id = target_farm
      AND g.is_active);
END
$$;

-- A field is visible when the caller can see its row, so the field's own farm policy decides.
CREATE OR REPLACE FUNCTION sc_field_visible(target_field TEXT) RETURNS BOOLEAN
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, public AS $$
BEGIN
  IF current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
     OR current_setting('app.current_role', true) = 'owner' THEN
    RETURN true;
  END IF;
  RETURN EXISTS (SELECT 1 FROM public.fields f WHERE f.field_id = target_field);
END
$$;
-- Write side: a granted farm only, never NULL (a NULL farm is visible to the whole tenant).
CREATE OR REPLACE FUNCTION sc_farm_writable(target_farm TEXT) RETURNS BOOLEAN
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, public AS $$
BEGIN
  IF current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
     OR current_setting('app.current_role', true) = 'owner' THEN
    RETURN true;
  END IF;
  RETURN target_farm IS NOT NULL AND sc_farm_visible(target_farm);
END
$$;

-- Write side for field-keyed rows: the field must be visible AND belong to a farm.
CREATE OR REPLACE FUNCTION sc_field_writable(target_field TEXT) RETURNS BOOLEAN
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, public AS $$
BEGIN
  IF current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
     OR current_setting('app.current_role', true) = 'owner' THEN
    RETURN true;
  END IF;
  RETURN EXISTS (
    SELECT 1 FROM public.fields f WHERE f.field_id = target_field AND f.farm_id IS NOT NULL);
END
$$;
-- Every role that reads these tables evaluates the policies (the default, stated explicitly).
GRANT EXECUTE ON FUNCTION sc_farm_visible(TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION sc_field_visible(TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION sc_farm_writable(TEXT) TO PUBLIC;
GRANT EXECUTE ON FUNCTION sc_field_writable(TEXT) TO PUBLIC;

DROP POLICY IF EXISTS sc_farm_scope ON farms;
CREATE POLICY sc_farm_scope ON farms AS RESTRICTIVE FOR ALL
    USING (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
           OR sc_farm_visible(farm_id::text))
    WITH CHECK (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
                OR sc_farm_writable(farm_id::text));
DROP POLICY IF EXISTS sc_farm_scope ON fields;
CREATE POLICY sc_farm_scope ON fields AS RESTRICTIVE FOR ALL
    USING (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
           OR sc_farm_visible(farm_id::text))
    WITH CHECK (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
                OR sc_farm_writable(farm_id::text));
DROP POLICY IF EXISTS sc_farm_scope ON seasons;
CREATE POLICY sc_farm_scope ON seasons AS RESTRICTIVE FOR ALL
    USING (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
           OR sc_field_visible(field_id::text))
    WITH CHECK (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
                OR sc_field_writable(field_id::text));
DROP POLICY IF EXISTS sc_farm_scope ON field_tasks;
CREATE POLICY sc_farm_scope ON field_tasks AS RESTRICTIVE FOR ALL
    USING (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
           OR sc_field_visible(field_id::text))
    WITH CHECK (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
                OR sc_field_writable(field_id::text));
DROP POLICY IF EXISTS sc_farm_scope ON farm_ledger_entries;
CREATE POLICY sc_farm_scope ON farm_ledger_entries AS RESTRICTIVE FOR ALL
    USING (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
           OR (sc_farm_visible(farm_id) AND (field_id IS NULL OR sc_field_visible(field_id))))
    WITH CHECK (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
                OR (sc_farm_writable(farm_id) AND (field_id IS NULL OR sc_field_writable(field_id))));

-- A non-owner deletes only what it may write (delta review B): DELETE checks USING only, so the
-- WITH CHECK above alone left farm-less rows deletable by anyone in the tenant.
DROP POLICY IF EXISTS sc_farm_scope_delete ON farms;
CREATE POLICY sc_farm_scope_delete ON farms AS RESTRICTIVE FOR DELETE
    USING (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
           OR sc_farm_writable(farm_id::text));
DROP POLICY IF EXISTS sc_farm_scope_delete ON fields;
CREATE POLICY sc_farm_scope_delete ON fields AS RESTRICTIVE FOR DELETE
    USING (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
           OR sc_farm_writable(farm_id::text));
DROP POLICY IF EXISTS sc_farm_scope_delete ON seasons;
CREATE POLICY sc_farm_scope_delete ON seasons AS RESTRICTIVE FOR DELETE
    USING (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
           OR sc_field_writable(field_id::text));
DROP POLICY IF EXISTS sc_farm_scope_delete ON field_tasks;
CREATE POLICY sc_farm_scope_delete ON field_tasks AS RESTRICTIVE FOR DELETE
    USING (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
           OR sc_field_writable(field_id::text));
DROP POLICY IF EXISTS sc_farm_scope_delete ON farm_ledger_entries;
CREATE POLICY sc_farm_scope_delete ON farm_ledger_entries AS RESTRICTIVE FOR DELETE
    USING (current_setting('app.enforce_farm_scope', true) IS DISTINCT FROM 'on'
           OR (sc_farm_writable(farm_id) AND (field_id IS NULL OR sc_field_writable(field_id))));

COMMIT;
