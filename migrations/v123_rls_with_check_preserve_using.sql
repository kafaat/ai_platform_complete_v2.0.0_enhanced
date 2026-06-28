-- v123: RLS write-path hardening — qual-preserving successor to v122.
--
-- Context:
--   v122 backfilled WITH CHECK on tenant write policies but it REPLACED each
--   policy's USING qual with a freshly-constructed tenant-only predicate. For the
--   policies it actually touched (pure `tenant_isolation`, USING = tenant_id match)
--   this was equivalent, so no regression occurred. But the *pattern* is unsafe: a
--   compound policy lacking WITH CHECK — e.g. `USING (id = current_user OR tenant
--   OR admin)` — would have its ownership/role/service conditions silently dropped.
--
--   This migration establishes the corrected, qual-PRESERVING pattern and acts as a
--   forward safety net: for every public tenant-aware write policy still missing
--   WITH CHECK, it adds WITH CHECK derived from the policy's EXISTING USING qual
--   (PostgreSQL's own default semantics) WITHOUT modifying USING. Ownership/role/
--   service-context conditions are preserved verbatim.
--
-- Notes:
--   * Idempotent and safe to re-run. On a v122-applied schema this is a no-op —
--     every tenant write policy already carries WITH CHECK — so it never weakens an
--     existing (deliberately distinct) WITH CHECK such as v97's `user_self`.
--   * Reuses public.sahool_effective_tenant_id() from v122 (no redefinition).
--   * MUST remain the LAST MANIFEST.txt entry (catalog-driven; runs after every
--     policy-creating migration so it sees the final policy set).

DO $$
DECLARE
    pol record;
BEGIN
    FOR pol IN
        SELECT p.schemaname, p.tablename, p.policyname, p.qual
        FROM pg_policies p
        JOIN information_schema.columns c
          ON c.table_schema = p.schemaname
         AND c.table_name = p.tablename
         AND c.column_name = 'tenant_id'
        WHERE p.schemaname = 'public'
          AND p.cmd IN ('ALL', 'INSERT', 'UPDATE')
          AND p.with_check IS NULL
          AND p.qual IS NOT NULL
          AND (
              p.qual ILIKE '%tenant_id%'
              OR p.qual ILIKE '%app.current_tenant%'
              OR p.qual ILIKE '%app.tenant_id%'
          )
    LOOP
        -- Preserve USING (pol.qual) verbatim; mirror it into WITH CHECK so every
        -- condition (ownership/role/service/tenant) governs writes too.
        EXECUTE format(
            'ALTER POLICY %I ON %I.%I USING (%s) WITH CHECK (%s)',
            pol.policyname,
            pol.schemaname,
            pol.tablename,
            pol.qual,
            pol.qual
        );
    END LOOP;
END $$;

-- Guard: no tenant-aware write policy may remain without WITH CHECK after v123.
DO $$
DECLARE
    offenders text;
BEGIN
    SELECT string_agg(
               format('%I.%I:%I', p.schemaname, p.tablename, p.policyname),
               ', ' ORDER BY p.schemaname, p.tablename, p.policyname
           )
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
        RAISE EXCEPTION 'tenant RLS write policies missing WITH CHECK after v123: %', offenders;
    END IF;
END $$;
