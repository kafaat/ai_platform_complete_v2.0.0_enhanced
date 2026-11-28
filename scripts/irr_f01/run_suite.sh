#!/usr/bin/env bash
# Both entry points run these same required cases and validate the actual JUnit file.
set -euo pipefail
export IRR_F01_SUITE="${1:?fresh or upgrade required}" IRR_F01_CERTIFICATION_REQUIRED=1
shift
cd "$(dirname "$0")/../.."
export ADMIN_DATABASE_URL="${TEST_DATABASE_ADMIN_URL:?admin DSN required}"
export APP_DATABASE_URL="${TEST_DATABASE_URL:?writer DSN required}"
: "${OTHER_TENANT_DATABASE_URL:?reader DSN required}"
report_dir="${REPORT_DIR:-${RUNNER_TEMP:-/tmp}/irr-f01}"
mkdir -p "$report_dir"
files=(tests_v9/test_irr_f01_reservation_live_pg.py)
case "$IRR_F01_SUITE" in
  fresh)
    files+=(tests/integration/irrigation/test_v195_postgres.py
            tests_v9/test_irr_f01_compensation_live_pg.py
            tests/irrigation/test_irrigation_capacity_reservation.py
            tests/irrigation/test_irrigation_reservation_adapter.py
            tests/irrigation/test_irrigation_v195_capacity_reservation_core.py)
    ;;
  upgrade)
    export IRR_F01_UPGRADE_DATABASE_URL="$TEST_DATABASE_URL"
    export IRR_F01_UPGRADE_ADMIN_URL="$TEST_DATABASE_ADMIN_URL"
    files+=(tests_v9/test_irr_f01_upgrade_gate_u1_pg.py)
    ;;
  *) exit 2 ;;
esac
# The local lab's pytest shim supplies its own JUnit path; the plugin reads pytest's
# resolved path so the same check runs in CI, the lab and a developer checkout.
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
pytest -q -rs -p scripts.irr_f01.required_cases --junitxml="$report_dir/$IRR_F01_SUITE.xml" "${files[@]}" "$@"
