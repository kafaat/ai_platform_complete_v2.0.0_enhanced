#!/usr/bin/env bash
set -Eeuo pipefail
# Only run on a designated staging database; do not pass DB passwords in args.
if [[ "${SCOUT_ACCEPTANCE_ENV:-}" != staging ]]; then
  echo 'REFUSED: SCOUT_ACCEPTANCE_ENV=staging required' >&2
  exit 64
fi
command -v psql >/dev/null 2>&1 || {
  echo 'NOT_RUN: psql unavailable; database acceptance remains OPEN' >&2
  exit 69
}
for var in PGHOST PGDATABASE PGUSER; do
  [[ -n "${!var:-}" ]] || { echo "REFUSED: missing $var" >&2; exit 64; }
done
scriptdir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Run all older gates first, then new constraints and scoped grants.
psql -X -w -v ON_ERROR_STOP=1 -f "$scriptdir/scout_photo_stage8_catalog_gate.sql"
psql -X -w -v ON_ERROR_STOP=1 -f "$scriptdir/scout_photo_stage9_catalog_gate.sql"
