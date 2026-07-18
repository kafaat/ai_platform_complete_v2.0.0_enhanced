\set ON_ERROR_STOP on
-- Live certification assertions for the runtime role boundary.
DO $$
DECLARE
    app record;
BEGIN
    SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole
      INTO app
      FROM pg_roles
     WHERE rolname = 'sahool_app';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'sahool_app role is missing';
    END IF;
    IF app.rolsuper OR app.rolbypassrls OR app.rolcreatedb OR app.rolcreaterole THEN
        RAISE EXCEPTION 'sahool_app has forbidden role attributes: %', row_to_json(app);
    END IF;
    IF has_schema_privilege('sahool_app', 'public', 'CREATE') THEN
        RAISE EXCEPTION 'sahool_app must not have CREATE on schema public';
    END IF;
    -- The privileged object owner / migration identity in the real role model is
    -- `sahool_user` (superuser, per migrations/apply_in_compose.sh). Assert the
    -- runtime role is NOT a member of it. Guard the check so it never raises on a
    -- deployment where the role is named differently or absent.
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahool_user')
       AND pg_has_role('sahool_app', 'sahool_user', 'MEMBER') THEN
        RAISE EXCEPTION 'sahool_app must not be a member of the privileged migration owner sahool_user';
    END IF;
END $$;

-- No tenant table may be owned by the runtime role.
DO $$
DECLARE
    owned_count bigint;
BEGIN
    SELECT count(*) INTO owned_count
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_attribute a ON a.attrelid = c.oid
     WHERE n.nspname = 'public'
       AND c.relkind IN ('r','p')
       AND a.attname = 'tenant_id'
       AND a.attnum > 0 AND NOT a.attisdropped
       AND pg_get_userbyid(c.relowner) = 'sahool_app';
    IF owned_count <> 0 THEN
        RAISE EXCEPTION 'sahool_app owns % tenant tables', owned_count;
    END IF;
END $$;
