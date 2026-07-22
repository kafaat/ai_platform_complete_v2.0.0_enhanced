#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
MODE="${MODE:-preflight}"
BASE_URL="${BASE_URL:-http://localhost}"
REPORT="${REPORT:-$ROOT/runtime_doctor_report.json}"
cd "$ROOT"
python scripts/runtime/env_doctor.py --root . --base-url "$BASE_URL" --mode "$MODE" --format json --output "$REPORT"
echo "Runtime doctor report written: $REPORT"
