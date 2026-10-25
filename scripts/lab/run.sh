#!/usr/bin/env bash
# Run the integration suite against the lab started by up.sh and write evidence.
#
#   bash scripts/lab/run.sh [extra pytest args]
#
# Writes $LAB_DIR/evidence/<UTC stamp>/ with lab_evidence.json, the JUnit XML and the
# logs. The JSON is DEV evidence, executor Claude or whoever runs it, independence
# none; it binds the commit, tree, image digests and dependency versions it measured.
# Copy that directory out before the container ends: nothing in $LAB_DIR persists.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
# shellcheck source=scripts/lab/lab.env
source scripts/lab/lab.env
venv="$LAB_DIR/venv"
[ -x "$venv/bin/python" ] || { echo "::error::LAB_NOT_UP: run scripts/lab/up.sh first" >&2; exit 1; }

out="$LAB_DIR/evidence/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$out"

export TEST_DATABASE_URL="postgresql://$LAB_PG_USER:$LAB_PG_PASSWORD@127.0.0.1:$LAB_PG_PORT/$LAB_PG_DB"
export TEST_REDIS_URL="redis://127.0.0.1:$LAB_REDIS_PORT/0"
# The same certification switches as the CI Integration Tests job: a missing
# database is a failure for these suites, not a skip.
export JWT_SECRET=test_secret_min_32_chars_for_sahool_v9
export CLAIM_LEASE_CERTIFICATION_REQUIRED=1 HIL_CERTIFICATION_REQUIRED=1
export RECONCILIATION_RESUMPTION_CERTIFICATION_REQUIRED=1 MIGRATOR_CERTIFICATION_REQUIRED=1

suites=(
  "integration|-m integration"
  "otel_pinned|tests_v9/test_otlp_tracing_delivery.py"
)
status=0
for entry in "${suites[@]}"; do
  name="${entry%%|*}"
  read -r -a args <<<"${entry#*|}"
  start=$(date +%s)
  "$venv/bin/python" -m pytest -p no:cacheprovider -q -rs "${args[@]}" "$@" \
    --junitxml="$out/$name.junit.xml" >"$out/$name.log" 2>&1
  rc=$?
  echo "$name rc=$rc seconds=$(($(date +%s) - start))" | tee -a "$out/suites.txt"
  [ "$rc" -eq 0 ] || status=1
done

"$venv/bin/python" -m pip freeze --all >"$out/pip_freeze.txt" 2>/dev/null
"$venv/bin/python" scripts/lab/write_evidence.py "$out" || status=1
echo "evidence: $out/lab_evidence.json"
exit "$status"
