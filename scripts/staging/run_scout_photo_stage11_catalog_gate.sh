#!/usr/bin/env bash
set -Eeuo pipefail
# Read-only PostgreSQL catalog checks on explicitly authorized staging ONLY.
# Requires a pre-migrated DB; it neither creates fixtures nor invokes migrations.
if [[ "${SCOUT_ACCEPTANCE_ENV:-}" != staging ]]; then
  echo 'REFUSED: stage11 catalog gate requires SCOUT_ACCEPTANCE_ENV=staging' >&2
  exit 64
fi
for key in PGHOST PGDATABASE PGUSER SCOUT_EXPECTED_STAGING_DB; do
  if [[ -z "${!key:-}" ]]; then
    echo "REFUSED: missing $key" >&2
    exit 64
  fi
done
if [[ "$PGDATABASE" != "$SCOUT_EXPECTED_STAGING_DB" ]]; then
  echo 'REFUSED: database identity does not match designated staging' >&2
  exit 64
fi
case "${PGDATABASE,,}" in
  *prod*|sahool|postgres|template0|template1)
    echo 'REFUSED: production or maintenance database name' >&2
    exit 64;;
esac
if ! command -v psql >/dev/null 2>&1; then
  echo 'NOT_RUN: PostgreSQL client unavailable' >&2
  exit 69
fi
scriptdir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-5}" psql -X -w -v ON_ERROR_STOP=1 \
  -f "$scriptdir/scout_photo_stage11_catalog_gate.sql"
