-- v122: RLS write-path hardening and tenant session-variable unification.
--
-- Context:
--   Older migrations used FOR ALL tenant policies with USING only.  That filters
--   visible rows but does not validate INSERT/UPDATE row values.  This backfill
--   amends every tenant RLS policy in public schema that lacks WITH CHECK.
--
--   It also normalizes the two historical session keys used by SAHOOL
--   (app.current_tenant and app.tenant_id).  The generated predicate accepts
--   either key, preferring app.current_tenant, so legacy writers and newer
--   Phase 9-12 workers share one effective tenant context.
--
-- Notes:
--   * Nullable tenant_id tables keep their historical NULL/system-row behavior.
--   * Non-null tenant_id tables become strict fail-closed writes.
--   * The migration is idempotent and safe to re-run.

CREATE OR REPLACE FUNCTION public.sahool_effective_tenant_id()
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT NULLIF(
        COALESCE(
            NULLIF(current_setting('app.current_tenant', true), ''),
            NULLIF(current_setting('app.tenant_id', true), '')
        ),
        ''
    )
$$;

COMMENT ON FUNCTION public.sahool_effective_tenant_id() IS
    'Returns the active tenant context. app.current_tenant is canonical; app.tenant_id is accepted for legacy Phase 9-12 writers.';

DO $$
DECLARE
    pol record;
    tenant_nullable boolean;
    predicate text;
BEGIN
    FOR pol IN
        SELECT p.schemaname, p.tablename, p.policyname, p.cmd, p.qual, p.with_check
        FROM pg_policies p
        JOIN information_schema.columns c
          ON c.table_schema = p.schemaname
         AND c.table_name = p.tablename
         AND c.column_name = 'tenant_id'
        WHERE p.schemaname = 'public'
          AND p.cmd IN ('ALL', 'INSERT', 'UPDATE')
          AND p.with_check IS NULL
          AND (
              p.qual ILIKE '%tenant_id%'
              OR p.qual ILIKE '%app.current_tenant%'
              OR p.qual ILIKE '%app.tenant_id%'
          )
    LOOP
        SELECT (c.is_nullable = 'YES')
          INTO tenant_nullable
          FROM information_schema.columns c
         WHERE c.table_schema = pol.schemaname
           AND c.table_name = pol.tablename
           AND c.column_name = 'tenant_id';

        IF tenant_nullable THEN
            predicate := '(tenant_id IS NULL OR tenant_id::text = public.sahool_effective_tenant_id())';
        ELSE
            predicate := '(tenant_id::text = public.sahool_effective_tenant_id())';
        END IF;

        EXECUTE format(
            'ALTER POLICY %I ON %I.%I USING (%s) WITH CHECK (%s)',
            pol.policyname,
            pol.schemaname,
            pol.tablename,
            predicate,
            predicate
        );
    END LOOP;
END $$;

-- Ensure every tenant-aware write policy is protected after the backfill.
DO $$
DECLARE
    offenders text;
BEGIN
    SELECT string_agg(format('%I.%I:%I', p.schemaname, p.tablename, p.policyname), ', ' ORDER BY p.schemaname, p.tablename, p.policyname)
      INTO offenders
      FROM pg_policies p
      JOIN information_schema.columns c
        ON c.table_schema = p.schemaname
       AND c.table_name = p.tablename
       AND c.column_name = 'tenant_id'
     WHERE p.schemaname = 'public'
       AND p.cmd IN ('ALL', 'INSERT', 'UPDATE')
       AND p.with_check IS NULL
       AND (
           p.qual ILIKE '%tenant_id%'
           OR p.qual ILIKE '%app.current_tenant%'
           OR p.qual ILIKE '%app.tenant_id%'
       );

    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION 'tenant RLS write policies missing WITH CHECK after v122: %', offenders;
    END IF;
END $$;
