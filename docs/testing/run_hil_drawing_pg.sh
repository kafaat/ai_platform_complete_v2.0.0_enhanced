#!/usr/bin/env bash
# Run on Linux with Docker. Uses only a newly created disposable local database.
# Usage: bash run_hil_drawing_pg.sh /absolute/repository/path [/path/to/test-venv/bin/python]
set -euo pipefail
repo="${1:?repository path required}"
proof_python="${2:-python3}"
cd "$repo"
command -v docker >/dev/null
"$proof_python" -c 'import asyncpg, pytest'
port="${HIL_LIVE_TEST_PORT:-65432}"
container=""
client_dir="$(mktemp -d)"
cleanup() {
  if [ -n "$container" ]; then
    docker rm -f "$container" >/dev/null 2>&1 || true
  fi
  rm -rf "$client_dir"
}
trap cleanup EXIT
# Fixed credentials are test-only and the port is bound to localhost.
container="$(docker run -d \
  -e POSTGRES_DB=sahool_test -e POSTGRES_USER=sahool_test \
  -e POSTGRES_PASSWORD=test_password \
  -p "127.0.0.1:${port}:5432" postgis/postgis:15-3.4)"
RUNNER_TEMP="$client_dir" bash scripts/ci/provision_pg_client.sh "$container"
export PATH="$client_dir/pg-client-shims:$PATH"
export PGPASSWORD=test_password
for attempt in $(seq 1 30); do
  pg_isready -h 127.0.0.1 -p "$port" -U sahool_test >/dev/null 2>&1 && break
  sleep 1
done
pg_isready -h 127.0.0.1 -p "$port" -U sahool_test
bash scripts/ci/apply_migration_manifest.sh --host 127.0.0.1 --port "$port" --user sahool_test --db sahool_test
bash scripts/ci/apply_migration_manifest.sh --host 127.0.0.1 --port "$port" --user sahool_test --db sahool_test
psql -h 127.0.0.1 -p "$port" -U sahool_test -d sahool_test -v ON_ERROR_STOP=1 <<'SQL'
CREATE ROLE sahool_app_test LOGIN PASSWORD 'app_test_password'
  NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE sahool_test TO sahool_app_test;
GRANT USAGE ON SCHEMA public TO sahool_app_test;
REVOKE CREATE ON SCHEMA public FROM sahool_app_test;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sahool_app_test;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sahool_app_test;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO sahool_app_test;
SQL
admin_dsn="postgresql://sahool_test:test_password@127.0.0.1:${port}/sahool_test"
app_dsn="postgresql://sahool_app_test:app_test_password@127.0.0.1:${port}/sahool_test"
TEST_DATABASE_URL="$admin_dsn" HIL_CERTIFICATION_REQUIRED=1 \
  "$proof_python" -m pytest -v -m integration -rs \
  tests_v9/test_db_wiring.py::TestHILGetStatus::test_create_then_get_status
TEST_DATABASE_ADMIN_URL="$admin_dsn" TEST_DATABASE_URL="$app_dsn" \
  RLS_ISOLATION_CERTIFICATION_REQUIRED=1 \
  "$proof_python" -m pytest -v -m integration -rs tests_v9/test_rls_tenant_isolation_live_pg.py
