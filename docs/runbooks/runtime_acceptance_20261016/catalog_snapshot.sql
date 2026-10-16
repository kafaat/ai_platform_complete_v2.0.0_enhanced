-- Read-only metadata receipt. Run with a separately authorized observation identity.
-- No user rows, role passwords, tenant IDs, secrets, DDL or persistent settings.
-- A catalog row is not evidence of restricted-role behavioral isolation.
\set ON_ERROR_STOP on
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '2s';
SET LOCAL search_path = pg_catalog;
SELECT current_database() AS database_name, current_user AS observation_role,
       current_setting('server_version_num') AS server_version_num,
       current_setting('transaction_read_only') AS transaction_read_only,
       clock_timestamp() AS observed_at;
SELECT rolname, rolsuper, rolbypassrls, rolcanlogin
FROM pg_roles WHERE rolname = current_user;
SELECT n.nspname, c.relname, pg_get_userbyid(c.relowner) AS owner,
       c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('decision_outbox_events', 'decision_reviews', 'online_learning_updates')
ORDER BY c.relname;
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN ('decision_outbox_events', 'decision_reviews', 'online_learning_updates')
ORDER BY tablename, policyname;
SELECT a.attname, format_type(a.atttypid, a.atttypmod) AS data_type,
       a.attnotnull, pg_get_expr(d.adbin, d.adrelid) AS default_expression
FROM pg_attribute a
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE a.attrelid = to_regclass('public.online_learning_updates')
  AND a.attname IN ('review_status', 'agronomically_approved', 'agronomic_review')
  AND NOT a.attisdropped
ORDER BY a.attname;
SELECT conname, convalidated, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = to_regclass('public.online_learning_updates')
  AND conname IN ('chk_oluj_agronomic_review_status', 'chk_oluj_agronomic_approval_consistency')
ORDER BY conname;
SELECT to_regclass('public.decision_service_schema_migrations') IS NOT NULL
       AS decision_migration_journal_present;
ROLLBACK;
