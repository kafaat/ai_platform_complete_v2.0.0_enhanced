-- SAHOOL v287 down — removes the farm-scope policies, their functions and farm_access_grants.
-- Destroys the stored grants. While enforcement was off (the default) visibility is unchanged;
-- if SAHOOL_FARM_SCOPE_ENFORCE was on, turn it off first: the platform stops setting
-- app.enforce_farm_scope once the objects are gone (api/farm_scope.py asks the catalog).
BEGIN;
SET LOCAL lock_timeout = '15s';
DROP POLICY IF EXISTS sc_farm_scope ON farm_ledger_entries;
DROP POLICY IF EXISTS sc_farm_scope ON field_tasks;
DROP POLICY IF EXISTS sc_farm_scope ON seasons;
DROP POLICY IF EXISTS sc_farm_scope ON fields;
DROP POLICY IF EXISTS sc_farm_scope ON farms;
DROP FUNCTION IF EXISTS sc_field_visible(TEXT);
DROP FUNCTION IF EXISTS sc_farm_visible(TEXT);
DROP TABLE IF EXISTS farm_access_grants;
COMMIT;
