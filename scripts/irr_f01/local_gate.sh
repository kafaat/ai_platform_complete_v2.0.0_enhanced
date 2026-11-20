#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
REPORT_DIR="${REPORT_DIR:-$ROOT/artifacts/irr-f01-local-test}"
mkdir -p "$REPORT_DIR"
# A failed rerun must never package an earlier green report.
export REPORT_DIR="$(mktemp -d "$REPORT_DIR/run-XXXXXXXX")"
export IRR_F01_SQLSTATE_FILE="$REPORT_DIR/failed-sql-state.json"
backend="${IRR_F01_BACKEND:-compose}"
stage=preflight
owned="$(mktemp -d)"
compose=()
started=false
finish() {
  rc=$?
  trap - EXIT
  set +e
  if [[ "$started" == true && "$backend" == compose ]]; then
    "${compose[@]}" logs postgres >"$REPORT_DIR/postgres.log" 2>&1
    "${compose[@]}" down -v >>"$REPORT_DIR/cleanup.log" 2>&1 || rc=1
  elif [[ "$started" == true && -f "$owned/db/postmaster.pid" ]]; then
    pg_ctl -D "$owned/db" -m fast -w stop >>"$REPORT_DIR/cleanup.log" 2>&1 || rc=1
  fi
  if [[ ! -f "$owned/db/postmaster.pid" ]]; then rm -rf "$owned"; fi
  status=failed
  if (( rc == 0 )); then status=passed; fi
  python scripts/irr_f01/build_report.py --report-dir "$REPORT_DIR" --status "$status" --stage "$stage" --exit-code "$rc" || rc=1
  (cd "$REPORT_DIR" && zip -q IRR_F01_LOCAL_GATE_ARTIFACTS.zip ./*) || rc=1
  echo "IRR-F01 evidence: $REPORT_DIR"
  exit "$rc"
}
trap finish EXIT

python -c 'import asyncpg, httpx, jwt, pytest, pytest_asyncio; print("pytest", pytest.__version__, "pytest-asyncio", pytest_asyncio.__version__, "asyncpg", asyncpg.__version__)' | tee "$REPORT_DIR/preflight.log"
command -v zip >/dev/null
export PGHOST=127.0.0.1 ADMIN_USER=postgres ADMIN_PASS=postgres PGPASSWORD=postgres
export U1_DB=sahool_u1_upgrade APP_ROLE=irr_f01_writer APP_PASS=irr_f01_writer
# docker exec runs psql beside the server; SQL file arguments resolve in the checkout.
case "$backend" in
  compose)
    # Compose project names must be lowercase.
    project="$(basename "$owned" | tr '[:upper:].' '[:lower:]-')"
    compose=(docker compose -p "irr-f01-$project" -f docker-compose.irr-f01-test.yml)
    stage=postgres_start
    started=true
    "${compose[@]}" up -d --wait --wait-timeout 90 postgres
    PGPORT="$("${compose[@]}" port postgres 5432 | awk -F: 'END {print $NF}')"
    db_command() {
      "${compose[@]}" exec -T -w /checkout -e PGPASSWORD -e PGHOST -e PGPORT=5432 \
        -e ADMIN_USER -e ADMIN_PASS -e U1_DB -e APP_ROLE -e APP_PASS postgres "$@"
    }
    db_port=5432
    ;;
  native)
    for exe in initdb pg_ctl psql pg_dump; do command -v "$exe" >/dev/null; done
    stage=postgres_start
    PGPORT="$(python -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"
    printf '%s\n' "$ADMIN_PASS" >"$owned/password"
    initdb -D "$owned/db" -U postgres --encoding=UTF8 --locale=C --auth=scram-sha-256 \
      --pwfile="$owned/password" >"$REPORT_DIR/initdb.log"
    started=true
    pg_ctl -D "$owned/db" -l "$REPORT_DIR/postgres.log" -o "-h 127.0.0.1 -p $PGPORT -c unix_socket_directories=''" -w start
    db_command() { "$@"; }
    db_port="$PGPORT"
    ;;
  *) echo "Unknown IRR_F01_BACKEND: $backend" >&2; exit 2 ;;
esac
export PGPORT
sql=(psql -X -h 127.0.0.1 -p "$db_port" -U postgres -d sahool_irr_test -v ON_ERROR_STOP=1)
stage=migration
db_command psql -X -h 127.0.0.1 -p "$db_port" -U postgres -d postgres -v ON_ERROR_STOP=1 \
  -c 'CREATE DATABASE sahool_irr_test TEMPLATE template0'
db_command bash scripts/ci/apply_migration_manifest.sh --host 127.0.0.1 --port "$db_port" \
  --user postgres --db sahool_irr_test >"$REPORT_DIR/migration-output.log" 2>&1
sed -nE 's/^migration\[[0-9]+\/[0-9]+\] (.+)$/\1/p' "$REPORT_DIR/migration-output.log" >"$REPORT_DIR/applied.txt"
grep -vE '^[[:space:]]*(#|$)' migrations/MANIFEST.txt >"$REPORT_DIR/expected.txt"
diff -u "$REPORT_DIR/expected.txt" "$REPORT_DIR/applied.txt"
IRR_F01_POSTGRES_VERSION="$(db_command "${sql[@]}" -Atc "SELECT current_setting('server_version') || ', PostGIS ' || postgis_lib_version()")"
export IRR_F01_POSTGRES_VERSION
echo "$IRR_F01_POSTGRES_VERSION" | tee -a "$REPORT_DIR/preflight.log"
[[ "$IRR_F01_POSTGRES_VERSION" == 15.* ]]
db_command "${sql[@]}" -v writer="$APP_ROLE" -v writer_pass="$APP_PASS" -f scripts/irr_f01/bootstrap.sql
db_command pg_dump -h 127.0.0.1 -p "$db_port" -U postgres --schema-only --no-owner --no-privileges sahool_irr_test >"$REPORT_DIR/schema-snapshot.sql"

run_tests() {
  local suite="$1" db="$2"
  TEST_DATABASE_ADMIN_URL="postgresql://postgres:postgres@127.0.0.1:$PGPORT/$db" \
  TEST_DATABASE_URL="postgresql://$APP_ROLE:$APP_PASS@127.0.0.1:$PGPORT/$db" \
  OTHER_TENANT_DATABASE_URL="postgresql://irr_f01_reader:irr_f01_reader@127.0.0.1:$PGPORT/$db" \
    bash scripts/irr_f01/run_suite.sh "$suite" 2>&1 | tee -a "$REPORT_DIR/pytest-output.log"
}
stage=fresh
run_tests fresh sahool_irr_test
stage=upgrade
db_command bash scripts/irr_f01/upgrade_gate_u1.sh >"$REPORT_DIR/upgrade-output.log" 2>&1
run_tests upgrade "$U1_DB"
stage=complete
