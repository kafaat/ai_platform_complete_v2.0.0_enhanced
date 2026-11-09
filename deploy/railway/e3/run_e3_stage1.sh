#!/usr/bin/env bash
# E3 stage 1 on the production-equivalent engine (postgis/postgis:15-3.4):
# the same steps as CI's Integration Tests job, minus Redis, on an isolated database.
# Output: a summary, sha256 receipts, and the JUnit reports (gzip+base64) in the log.
set -uo pipefail
: "${PGHOST:?}" "${PGPORT:?}" "${PGUSER:?}" "${PGPASSWORD:?}" "${PGDATABASE:?}" "${APP_TEST_PASSWORD:?}"
cd "$(dirname "$(readlink -f "$0")")/../../.."
OUT=/tmp/e3; mkdir -p "$OUT"
sha="${RAILWAY_GIT_COMMIT_SHA:-unknown}"
echo "E3_BEGIN sha=${sha} host=${PGHOST} db=${PGDATABASE} at=$(date -u +%FT%TZ)"

for i in $(seq 1 60); do pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1 && break; sleep 2; done
pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" || { echo "E3_FAIL reason=db_unreachable"; exit 1; }
psql -X -Atc "select 'E3_ENGINE ' || version()" ; psql -X -Atc "select 'E3_POSTGIS ' || postgis_full_version()"

status=0
step() { local name="$1"; shift; echo "E3_STEP_BEGIN ${name}"; if "$@"; then echo "E3_STEP_PASS ${name}"; else rc=$?; echo "E3_STEP_FAIL ${name} rc=${rc}"; status=1; fi; }

step migrate_apply bash scripts/ci/apply_migration_manifest.sh --host "$PGHOST" --port "$PGPORT" --user "$PGUSER" --db "$PGDATABASE"
tables=$(psql -X -Atc "select count(*) from information_schema.tables where table_schema='public'")
echo "E3_SCHEMA public_tables=${tables}"
[ "${tables:-0}" -gt 0 ] || { echo "E3_STEP_FAIL schema_created tables=${tables}"; status=1; }
step migrate_reapply bash scripts/ci/apply_migration_manifest.sh --host "$PGHOST" --port "$PGPORT" --user "$PGUSER" --db "$PGDATABASE"
tables2=$(psql -X -Atc "select count(*) from information_schema.tables where table_schema='public'")
echo "E3_SCHEMA_AFTER_REAPPLY public_tables=${tables2}"

step restricted_role psql -X -v ON_ERROR_STOP=1 -v pw="$APP_TEST_PASSWORD" -v db="$PGDATABASE" <<'SQL'
SELECT format('CREATE ROLE sahool_app_test LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOINHERIT', :'pw')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahool_app_test') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO sahool_app_test', :'db') \gexec
GRANT USAGE ON SCHEMA public TO sahool_app_test;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sahool_app_test;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sahool_app_test;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO sahool_app_test;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sahool_app_test;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO sahool_app_test;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO sahool_app_test;
SQL
flags=$(psql -X -Atc "select rolsuper::text||':'||rolbypassrls::text from pg_roles where rolname='sahool_app_test'")
echo "E3_ROLE_FLAGS ${flags}"; [ "$flags" = "false:false" ] || { echo "E3_STEP_FAIL role_flags"; status=1; }

enc() { python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$1"; }
export TEST_DATABASE_ADMIN_URL="postgresql://${PGUSER}:$(enc "$PGPASSWORD")@${PGHOST}:${PGPORT}/${PGDATABASE}"
export TEST_DATABASE_URL="postgresql://sahool_app_test:$(enc "$APP_TEST_PASSWORD")@${PGHOST}:${PGPORT}/${PGDATABASE}"
for t in test_irr_f01_reservation_live_pg test_h51_field_source_binding_pg test_rls_tenant_isolation_live_pg \
         test_imagery_automation_rls_live_pg test_d1_raster_queue_rls_live_pg; do
  step "pytest_${t}" python -m pytest -p no:cacheprovider -m integration -rs -q "tests_v9/${t}.py" --junitxml="$OUT/${t}.xml"
done

echo "E3_RECEIPTS_BEGIN"; (cd "$OUT" && sha256sum ./*.xml); echo "E3_RECEIPTS_END"
python3 - "$OUT" <<'PY'
import sys, glob, os, xml.etree.ElementTree as ET
tot = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
for f in sorted(glob.glob(os.path.join(sys.argv[1], "*.xml"))):
    r = ET.parse(f).getroot(); s = r if r.tag == "testsuite" else r.find("testsuite")
    c = {k: int(s.get(k, 0)) for k in tot}; [tot.__setitem__(k, tot[k] + c[k]) for k in tot]
    print("E3_JUNIT", os.path.basename(f), c)
print("E3_JUNIT_TOTAL", tot)
PY
echo "E3_ARTIFACT_BEGIN"; tar -C "$OUT" -czf - . | base64 -w 0; echo; echo "E3_ARTIFACT_END"
echo "E3_END status=${status} sha=${sha} at=$(date -u +%FT%TZ)"
exit "$status"
