#!/usr/bin/env bash
# IRR-F01 Gate U1 — v194→v195/v196 UPGRADE certification (as opposed to fresh-schema).
#
# Builds a database with the FULL migration chain applied *only through v194*, seeds
# realistic legacy irrigation data (water source → well → pump; project → hydraulic
# nodes → canonical capability), then applies v195 + v196 ON TOP and certifies that the
# upgrade is lossless and structurally sound:
#   * every legacy row survives (counts unchanged),
#   * the v195 capacity/reservation tables + v196 target-binding table now exist,
#   * v195's uq_canonical_hydraulic_capability_tenant index (which backs the tenant-scoped
#     composite FK) builds successfully over the PRE-EXISTING capability row,
#   * re-applying v195 + v196 is idempotent (IF NOT EXISTS / CREATE OR REPLACE / DROP …
#     IF EXISTS everywhere) — a second apply is a clean no-op,
#   * no illegal NULLs leaked into the new tables.
#
# It then GRANTs a restricted NOSUPERUSER/NOBYPASSRLS app role so the caller can run
# Gate A / Gate B1 (the live reservation gates) over this UPGRADED database — that live
# run is the second half of the certification and is driven by the CI step / runbook,
# not by this script.
#
# The seed uses FIXED identifiers (below) so the Python upgrade test
# (tests_v9/test_irr_f01_upgrade_gate_u1_pg.py) can reference the legacy capability and
# certify the v195 composite FK over data that predates v195.
#
# Env (all have safe local defaults; CI overrides PGPORT/passwords):
#   PGHOST PGPORT ADMIN_USER ADMIN_PASS U1_DB APP_ROLE APP_PASS
set -euo pipefail

PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
ADMIN_USER="${ADMIN_USER:-sahool_test}"
ADMIN_PASS="${ADMIN_PASS:-test_password}"
U1_DB="${U1_DB:-sahool_u1_upgrade}"
APP_ROLE="${APP_ROLE:-sahool_app_test}"
APP_PASS="${APP_PASS:-app_test_password}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MANIFEST="$ROOT/migrations/MANIFEST.txt"

# --- fixed legacy identifiers (kept in sync with the Python upgrade test) ---------------
U1_TENANT="11111111-1111-1111-1111-111111111111"
U1_PROJECT="22222222-2222-2222-2222-222222222222"
U1_SOURCE="33333333-3333-3333-3333-333333333333"
U1_WELL="44444444-4444-4444-4444-444444444444"
U1_PUMP="55555555-5555-5555-5555-555555555555"
U1_NODE1="66666666-6666-6666-6666-666666666666"
U1_NODE2="77777777-7777-7777-7777-777777777777"
U1_CAP_ID="u1-capability-legacy"
U1_CAP_DIGEST="cf689961300e0ade7f5bfa7b348bd67c7e450d84ed939c743737cb74d47b31e9"

export PGPASSWORD="$ADMIN_PASS"
psql_admin() { psql -h "$PGHOST" -p "$PGPORT" -U "$ADMIN_USER" -v ON_ERROR_STOP=1 "$@"; }
db() { psql_admin -d "$U1_DB" "$@"; }
scalar() { db -Atc "$1"; }

echo "== Gate U1: (re)create $U1_DB =="
psql_admin -d postgres -c "DROP DATABASE IF EXISTS $U1_DB WITH (FORCE)" >/dev/null 2>&1 \
  || psql_admin -d postgres -c "DROP DATABASE IF EXISTS $U1_DB" >/dev/null
psql_admin -d postgres -c "CREATE DATABASE $U1_DB OWNER $ADMIN_USER" >/dev/null

echo "== Gate U1: apply migration chain through v194 only =="
# المُشغّل القانونيّ وحده يملك التعداد. كانت هنا نسخةٌ ثالثة من الحلقة المعطوبة،
# فطبعت `applied 1 migrations (pre-v195)` في 32290853228 ثمّ سقطت البذرة بـ
# `relation "irrigation_projects" does not exist` — نفس تصادم ملكيّة المجرى.
bash "$ROOT/scripts/ci/apply_migration_manifest.sh" \
  --root "$ROOT" --manifest "$MANIFEST" \
  --host "$PGHOST" --port "$PGPORT" --user "$ADMIN_USER" --db "$U1_DB" \
  --stop-before 'v195_*|v196_*'

# The v195 tables MUST NOT exist yet — proves we truly stopped before the upgrade.
for t in hydraulic_capacity_evaluations irrigation_resource_reservations \
         irrigation_resource_reservation_events irrigation_target_bindings; do
  [ "$(scalar "SELECT to_regclass('$t') IS NULL")" = "t" ] \
    || { echo "::error::$t already exists before v195 — chain did not stop at v194"; exit 1; }
done

echo "== Gate U1: seed realistic legacy data (pre-upgrade) =="
db >/dev/null <<SQL
INSERT INTO irrigation_projects(id, tenant_id, name)
  VALUES ('$U1_PROJECT', '$U1_TENANT', 'u1-legacy-project');
INSERT INTO irrigation_water_sources(id, tenant_id, project_id, source_type, name)
  VALUES ('$U1_SOURCE', '$U1_TENANT', '$U1_PROJECT', 'well', 'u1-source');
INSERT INTO irrigation_wells(id, tenant_id, water_source_id, name)
  VALUES ('$U1_WELL', '$U1_TENANT', '$U1_SOURCE', 'u1-well');
INSERT INTO irrigation_pumps(id, tenant_id, project_id, water_source_id, well_id, name, pump_type)
  VALUES ('$U1_PUMP', '$U1_TENANT', '$U1_PROJECT', '$U1_SOURCE', '$U1_WELL', 'u1-pump', 'submersible');
INSERT INTO irrigation_hydraulic_nodes(id, tenant_id, project_id, node_type, elevation_m)
  VALUES ('$U1_NODE1', '$U1_TENANT', '$U1_PROJECT', 'pump', 0),
         ('$U1_NODE2', '$U1_TENANT', '$U1_PROJECT', 'valve', 0);
INSERT INTO canonical_hydraulic_capabilities(
    capability_id, tenant_id, project_id, well_id, pump_id, target_asset_id,
    status, operational_eligible, capability_digest, payload)
  VALUES ('$U1_CAP_ID', '$U1_TENANT', '$U1_PROJECT', '$U1_WELL', '$U1_PUMP', 'u1-target',
          'verified', true, '$U1_CAP_DIGEST', '{}'::jsonb);
SQL

pre_proj=$(scalar "SELECT count(*) FROM irrigation_projects")
pre_src=$(scalar "SELECT count(*) FROM irrigation_water_sources")
pre_well=$(scalar "SELECT count(*) FROM irrigation_wells")
pre_pump=$(scalar "SELECT count(*) FROM irrigation_pumps")
pre_node=$(scalar "SELECT count(*) FROM irrigation_hydraulic_nodes")
pre_cap=$(scalar "SELECT count(*) FROM canonical_hydraulic_capabilities")
echo "   pre-upgrade counts: proj=$pre_proj src=$pre_src well=$pre_well pump=$pre_pump node=$pre_node cap=$pre_cap"

echo "== Gate U1: apply v195 then v196 (the upgrade) =="
db -f "$ROOT/migrations/v195_irrigation_capacity_reservation_core.sql" >/dev/null
db -f "$ROOT/migrations/v196_irrigation_target_binding.sql" >/dev/null

echo "== Gate U1: idempotent re-apply of v195 + v196 (must be a clean no-op) =="
db -f "$ROOT/migrations/v195_irrigation_capacity_reservation_core.sql" >/dev/null
db -f "$ROOT/migrations/v196_irrigation_target_binding.sql" >/dev/null

echo "== Gate U1: structural + no-data-loss assertions =="
for t in hydraulic_capacity_evaluations irrigation_resource_reservations \
         irrigation_resource_reservation_events irrigation_target_bindings; do
  [ "$(scalar "SELECT to_regclass('$t') IS NOT NULL")" = "t" ] \
    || { echo "::error::$t missing after upgrade"; exit 1; }
done
[ "$(scalar "SELECT count(*) FROM pg_indexes WHERE indexname='uq_canonical_hydraulic_capability_tenant'")" = "1" ] \
  || { echo "::error::uq_canonical_hydraulic_capability_tenant index missing after upgrade"; exit 1; }
[ "$(scalar "SELECT count(*) FROM pg_trigger WHERE tgname='trg_irrigation_reservation_events_append_only'")" = "1" ] \
  || { echo "::error::append-only trigger missing after upgrade"; exit 1; }

check_eq() { [ "$2" = "$3" ] || { echo "::error::data loss on $1: pre=$2 post=$3"; exit 1; }; }
check_eq projects "$pre_proj" "$(scalar "SELECT count(*) FROM irrigation_projects")"
check_eq water_sources "$pre_src" "$(scalar "SELECT count(*) FROM irrigation_water_sources")"
check_eq wells "$pre_well" "$(scalar "SELECT count(*) FROM irrigation_wells")"
check_eq pumps "$pre_pump" "$(scalar "SELECT count(*) FROM irrigation_pumps")"
check_eq nodes "$pre_node" "$(scalar "SELECT count(*) FROM irrigation_hydraulic_nodes")"
check_eq capabilities "$pre_cap" "$(scalar "SELECT count(*) FROM canonical_hydraulic_capabilities")"

# The legacy capability survived intact with its original digest.
[ "$(scalar "SELECT capability_digest FROM canonical_hydraulic_capabilities WHERE capability_id='$U1_CAP_ID'")" = "$U1_CAP_DIGEST" ] \
  || { echo "::error::legacy capability digest changed by upgrade"; exit 1; }
# No illegal NULLs leaked into the new (empty) tables' NOT NULL columns.
for t in hydraulic_capacity_evaluations irrigation_resource_reservations irrigation_resource_reservation_events; do
  [ "$(scalar "SELECT count(*) FROM $t WHERE tenant_id IS NULL")" = "0" ] \
    || { echo "::error::NULL tenant_id present in $t"; exit 1; }
done

echo "== Gate U1: grant restricted NOSUPERUSER/NOBYPASSRLS app role on $U1_DB =="
db >/dev/null <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$APP_ROLE') THEN
    CREATE ROLE $APP_ROLE LOGIN PASSWORD '$APP_PASS' NOSUPERUSER NOBYPASSRLS NOINHERIT;
  END IF;
END \$\$;
GRANT CONNECT ON DATABASE $U1_DB TO $APP_ROLE;
GRANT USAGE ON SCHEMA public TO $APP_ROLE;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO $APP_ROLE;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO $APP_ROLE;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO $APP_ROLE;
SQL
role_flags=$(scalar "SELECT rolsuper::text || ':' || rolbypassrls::text FROM pg_roles WHERE rolname='$APP_ROLE'")
test "$role_flags" = "false:false" || { echo "::error::invalid RLS role flags: $role_flags"; exit 1; }

echo "Gate U1 upgrade certification PASSED — $U1_DB is v196 over v194-seeded legacy data."
