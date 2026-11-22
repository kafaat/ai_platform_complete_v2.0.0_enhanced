-- SAHOOL v287 down — removes the farm-scope policies, their functions and farm_access_grants.
-- Destroys the stored grants. While enforcement was off (the default) visibility is unchanged;
-- if SAHOOL_FARM_SCOPE_ENFORCE was on, turn it off first. sahool-platform caches the PRESENCE
-- of v287 for its process lifetime (api/farm_scope.py: presence cached, absence asked again), so
-- with the flag still on it would keep reading farm_access_grants after this file and fail its
-- requests; with the flag off it reads nothing. Restart sahool-platform after this file to drop
-- the cached presence before the flag is ever switched on again.
BEGIN;
SET LOCAL lock_timeout = '15s';
DO $$ DECLARE t TEXT; BEGIN
  FOREACH t IN ARRAY ARRAY['farm_ledger_entries', 'field_tasks', 'seasons', 'fields', 'farms'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS sc_farm_scope_delete ON %I', t);
  END LOOP;
END $$;
DROP POLICY IF EXISTS sc_farm_scope ON farm_ledger_entries;
DROP POLICY IF EXISTS sc_farm_scope ON field_tasks;
DROP POLICY IF EXISTS sc_farm_scope ON seasons;
DROP POLICY IF EXISTS sc_farm_scope ON fields;
DROP POLICY IF EXISTS sc_farm_scope ON farms;
DROP FUNCTION IF EXISTS sc_field_writable(TEXT);
DROP FUNCTION IF EXISTS sc_farm_writable(TEXT);
DROP FUNCTION IF EXISTS sc_field_visible(TEXT);
DROP FUNCTION IF EXISTS sc_farm_visible(TEXT);
DROP TABLE IF EXISTS farm_access_grants;
DROP FUNCTION IF EXISTS farm_access_grant_provenance_guard();
COMMIT;
