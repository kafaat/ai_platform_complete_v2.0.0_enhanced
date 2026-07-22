#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT/docker-compose.irr-f01-test.yml"
REPORT_DIR="${REPORT_DIR:-$ROOT/artifacts/irr-f01-local-test}"
mkdir -p "$REPORT_DIR"
: > "$REPORT_DIR/pytest-output.log"
: > "$REPORT_DIR/migration-output.log"
: > "$REPORT_DIR/postgres.log"
echo '{}' > "$REPORT_DIR/failed-sql-state.json"
STATUS=failed; STAGE=preflight; RC=1

cleanup() {
  docker compose -f "$COMPOSE_FILE" logs postgres > "$REPORT_DIR/postgres.log" 2>&1 || true
  docker compose -f "$COMPOSE_FILE" down -v --remove-orphans >> "$REPORT_DIR/cleanup.log" 2>&1 || true
}
finish() {
  python "$ROOT/scripts/irr_f01/build_report.py" --report-dir "$REPORT_DIR" --status "$STATUS" --stage "$STAGE" --exit-code "$RC" || true
  (cd "$REPORT_DIR" && zip -qr IRR_F01_LOCAL_GATE_ARTIFACTS.zip .) || true
}
trap 'cleanup; finish' EXIT

for bin in docker python zip; do
  command -v "$bin" >/dev/null || { echo "missing dependency: $bin" | tee -a "$REPORT_DIR/preflight.log"; STATUS=not-certified; RC=127; exit "$RC"; }
done
docker compose version >> "$REPORT_DIR/preflight.log" 2>&1 || { STATUS=not-certified; RC=127; exit "$RC"; }

STAGE=postgres_start
docker compose -f "$COMPOSE_FILE" up -d --wait --wait-timeout 60 postgres > "$REPORT_DIR/postgres-start.log" 2>&1
PORT="$(docker compose -f "$COMPOSE_FILE" port postgres 5432 | sed -E 's/.*:([0-9]+)$/\1/')"
[[ "$PORT" =~ ^[0-9]+$ ]] || { echo "could not resolve mapped postgres port"; exit 1; }
export ADMIN_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:${PORT}/sahool_irr_test"
export APP_DATABASE_URL="postgresql://sahool_app:sahool_app@127.0.0.1:${PORT}/sahool_irr_test"
export OTHER_TENANT_DATABASE_URL="postgresql://sahool_other:sahool_other@127.0.0.1:${PORT}/sahool_irr_test"
export IRR_F01_SQLSTATE_FILE="$REPORT_DIR/failed-sql-state.json"
export IRR_F01_POSTGRES_VERSION="$(docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U postgres -d sahool_irr_test -Atc 'show server_version')"

STAGE=migration
{
  docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U postgres -d sahool_irr_test < "$ROOT/scripts/irr_f01/bootstrap.sql"
  # Apply the project migration chain in lexical/version order. The test fails at the first invalid dependency.
  while IFS= read -r f; do
    docker compose -f "$COMPOSE_FILE" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d sahool_irr_test < "$f"
  done < <(find "$ROOT/migrations" -maxdepth 1 -type f -name 'v*.sql' -print | sort -V)
  docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U postgres -d sahool_irr_test <<'SQL'
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO sahool_app, sahool_other;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sahool_app, sahool_other;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('sahool_app','sahool_other') AND (rolsuper OR rolbypassrls)) THEN
    RAISE EXCEPTION 'RLS test role is superuser or BYPASSRLS';
  END IF;
END $$;
SQL
} > "$REPORT_DIR/migration-output.log" 2>&1

docker compose -f "$COMPOSE_FILE" exec -T postgres pg_dump -U postgres --schema-only --no-owner --no-privileges sahool_irr_test > "$REPORT_DIR/schema-snapshot.sql" 2> "$REPORT_DIR/schema-snapshot.err" || true

STAGE=tests
set +e
python -m pytest \
  "$ROOT/tests/irrigation/test_irrigation_capacity_reservation.py" \
  "$ROOT/tests/irrigation/test_irrigation_reservation_adapter.py" \
  "$ROOT/tests/irrigation/test_irrigation_v195_capacity_reservation_core.py" \
  "$ROOT/tests/integration/irrigation/test_v195_postgres.py" \
  -q --junitxml="$REPORT_DIR/pytest-junit.xml" 2>&1 | tee "$REPORT_DIR/pytest-output.log"
RC=${PIPESTATUS[0]}
set -e
if (( RC != 0 )); then STATUS=failed; exit "$RC"; fi
STATUS=passed; STAGE=complete; RC=0
