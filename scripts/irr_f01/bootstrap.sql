\set ON_ERROR_STOP on
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sahool_app') THEN
    CREATE ROLE sahool_app LOGIN PASSWORD 'sahool_app' NOSUPERUSER NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sahool_other') THEN
    CREATE ROLE sahool_other LOGIN PASSWORD 'sahool_other' NOSUPERUSER NOBYPASSRLS;
  END IF;
END $$;
GRANT CONNECT ON DATABASE sahool_irr_test TO sahool_app, sahool_other;
GRANT USAGE ON SCHEMA public TO sahool_app, sahool_other;
