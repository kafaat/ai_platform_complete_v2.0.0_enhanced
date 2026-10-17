#!/usr/bin/env bash
# Re-measurement commands for certification/evidence/architecture_remeasure_20261017.
# Read-only on the tree: every output goes to raw/ next to this script. Run from the repo root:
#   bash certification/evidence/architecture_remeasure_20261017/commands.sh
# Optional: NATS_SERVER_BIN=/path/to/nats-server (2.15.x) enables the live local-process NATS probe.
set -uo pipefail
HERE="certification/evidence/architecture_remeasure_20261017"
RAW="$HERE/raw"
mkdir -p "$RAW"
export PYTHONHASHSEED=0

run() { # name, command...
  local name="$1"; shift
  {
    echo "\$ $*"
    "$@"
    echo "[exit=$?]"
  } >"$RAW/$name.txt" 2>&1
}

{
  echo "sha=$(git rev-parse HEAD)"
  echo "origin_main=$(git rev-parse origin/main)"
  echo "date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "python=$(python3 --version 2>&1)"
} >"$RAW/00_head.txt"

# ── 1. OWNERSHIP-CONTRACT-DECLARED-BUT-NEVER-MEASURED-01 ───────────────────────
run 10_db_writer_ownership_guard python3 scripts/ci/db_writer_ownership_guard.py --check
run 11_ownership_extraction_alignment_guard python3 scripts/ci/ownership_extraction_alignment_guard.py
python3 "$HERE/measure_ownership.py" >"$HERE/ownership_remeasure.json" 2>"$RAW/12_measure_ownership.stderr.txt"
echo "[exit=$?]" >>"$RAW/12_measure_ownership.stderr.txt"
run 13_baseline_history git log --format='%h %ad %s' --date=short -6 -- docs/architecture/db_writer_ownership_baseline.json
run 14_baseline_diff_1205 git show f3fd099e9 -- docs/architecture/db_writer_ownership_baseline.json
# #1205 removed weather-polygon-worker: who writes / reads field_weather_overlay now (exit=1 => no match).
run 14a_field_weather_overlay_sql_writes git grep -n -i -E '(INSERT INTO|UPDATE|DELETE FROM) +field_weather_overlay' -- '*.py'
run 14b_field_weather_overlay_readers git grep -n -w field_weather_overlay -- services/weather-signal-engine services/weather-service
# M-03
run 15_m03_outbox_refs git grep -n actuator_command_outbox -- '*.py' '*.sql' '*.yml'
run 16_m03_dispatch_refs git grep -n iot_command_dispatch -- '*.py' '*.sql' '*.yml'
run 17_m03_dispatch_schema sed -n '5,23p' migrations/v109_phase9_iot_execution_adapters.sql
run 18_m03_dispatch_claim sed -n '455,512p' services/sahool-platform/api/phase_runtime_workers.py
run 19_m03_actuator_service_refs git grep -n -E 'iot_command_dispatch|actuator_command_outbox|dispatch\.requested' -- services/actuator-service

# ── 2. CONNECTIVITY-AUDIT-20260910 ─────────────────────────────────────────────
# Same 9-file selection the repair report ran (74 tests at 7407eae2).
run 20_conn_report_selection python3 -m pytest -q -p no:cacheprovider \
  tests_v9/test_connectivity_tile_transport.py \
  shared/gis/test_cloud_native_runtime.py \
  tests_v9/test_compose_nginx_upstream_contract.py \
  tests_v9/test_raster_tiler_service_contract.py \
  services/odoo-bridge/test_erp_readiness_granular.py \
  tests_v9/test_raster_field_tenant_authz.py \
  tests_v9/test_tilejson_nginx_runtime_fix_20260626.py \
  tests_v9/test_erp_bridge_alias_contract.py \
  tests_v9/test_erp_bridge_fail_closed.py
# CONN-03: static NATS identity/ACL/TLS contract + live probe when a nats-server binary is given.
run 21_conn03_nats_static python3 -m pytest -q -p no:cacheprovider -m unit \
  tests_v9/test_nats_least_privilege.py tests_v9/test_nats_tls_init.py \
  tests_v9/test_nats_subject_ownership_contract.py
if [ -n "${NATS_SERVER_BIN:-}" ]; then
  run 22a_conn03_nats_versions sh -c '"$NATS_SERVER_BIN" --version; python3 -c "import importlib.metadata as m; print(\"nats-py\", m.version(\"nats-py\"))"'
  NATS_LEAST_PRIVILEGE_LIVE_REQUIRED=1 run 22_conn03_nats_live_local_process \
    python3 -m pytest -q -p no:cacheprovider -rs tests_v9/test_nats_least_privilege.py
  # The Core-NATS publish witness races stream storage (contract residual 2); repeat it alone.
  NATS_LEAST_PRIVILEGE_LIVE_REQUIRED=1 run 22b_conn03_frozen_publisher_repeat sh -c 'for i in 1 2 3 4 5 6 7 8 9 10; do python3 -m pytest -q -p no:cacheprovider "tests_v9/test_nats_least_privilege.py::test_live_frozen_phase_worker_publishes_its_subject_and_a_refusal_is_silent" 2>&1 | tail -n 1; done'
else
  echo "SKIPPED: NATS_SERVER_BIN not set" >"$RAW/22_conn03_nats_live_local_process.txt"
fi
run 23_conn03_nats_conf_users grep -n -E 'user: |^tls|^authorization|default_permissions|no_auth_user' nats/nats.conf
run 24_conn03_compose_nats_urls grep -n -E 'image: nats|NATS_URL:|sahool-nats-tls-init:' docker-compose.v9.yml
run 25_conn03_other_compose_nats grep -n -A4 -E '^  (evidence-nats|test-nats):' docker-compose.evidence-lab.yml docker-compose.test.yml
run 26_conn03_exporter sed -n '3139,3151p' docker-compose.v9.yml
run 27_conn03_monitor_port grep -n -E '^http:|wget -qO- http://localhost:8222' nats/nats.conf docker-compose.v9.yml
run 28_conn03_actuator_subject sed -n '500,510p' services/sahool-platform/api/phase_runtime_workers.py
# CONN-04: producer transform vs canonical consumer, and the GATE-01 freeze.
run 30_conn04_producer sed -n '296,304p' services/sahool-platform/api/phase_runtime_workers.py
run 31_conn04_consumer sed -n '23,34p' shared/notification_consumers.py
run 32_conn04_acl sed -n '107,129p' nats/nats.conf
run 33_conn04_gate01 grep -n 'phase_runtime_workers' docs/architecture/gate01_policy.json
run 34_conn04_contract python3 -c "import json;d=json.load(open('docs/architecture/nats_subject_ownership_contract.json'));print(json.dumps({k:d['gaps'][k] for k in ('NATS-SUBJECT-NAMESPACE-CONTRACT-DIVERGENCE','AGENT-TO-ACTUATOR-ADAPTER-ABSENT')},ensure_ascii=False,indent=1))"
# CONN-07: native mobile projects.
run 40_conn07_native_files git ls-files mobile/sahool_app/android mobile/sahool_app/ios mobile/sahool_app/pubspec.lock
run 41_conn07_ci_job sed -n '2172,2197p' .github/workflows/ci.yml
run 42_conn07_ios_ci grep -n -E 'runs-on: macos|xcodebuild|flutter build (ios|ipa|appbundle)|flutter build apk --release' .github/workflows/ci.yml
run 44_conn07_lockfile_enforcement grep -n 'flutter pub get' .github/workflows/ci.yml
run 45_conn07_podfile_lock sh -c 'git ls-files mobile/sahool_app/ios | grep -c Podfile.lock; true'
run 43_conn07_signing grep -n -i -E 'signingConfig|release' mobile/sahool_app/android/app/build.gradle
# CONN-01/06/08 live parts: what this container can and cannot run.
run 50_live_tools sh -c 'command -v docker flutter nats-server; docker ps 2>&1 | head -1; true'
run 52_conn06_nginx_resolver grep -n -E '^resolver|server sahool-[a-z-]+:[0-9]+ resolve;' frontend/nginx.conf
run 53_conn03_production_compose_nats sh -c 'grep -c -i nats docker-compose.production.yml; true'
run 51_conn01_tiler_compose grep -n -A3 -E '^  raster-tiler-service:|raster-tiler-service:$' docker-compose.v9.yml

# ── 3. A-DECLARED-EDGE-WITHOUT-A-CALL-SITE-IS-NEITHER-PROVEN-NOR-ABSENT-01 baseline ──
python3 "$HERE/measure_edges.py" >"$HERE/edges_baseline.json" 2>"$RAW/60_measure_edges.stderr.txt"
echo "[exit=$?]" >>"$RAW/60_measure_edges.stderr.txt"
