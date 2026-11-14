#!/usr/bin/env bash
set -Eeuo pipefail
# Local staging preflight, read-only; never use secrets in process arguments.
# Set PGHOST PGPORT PGDATABASE PGUSER and a managed password service or .pgpass.
if [[ "${SCOUT_ACCEPTANCE_ENV:-}" != 'staging' ]]; then
  echo 'REFUSED: set SCOUT_ACCEPTANCE_ENV=staging; production/unclassified DB not accepted' >&2
  exit 64
fi
command -v psql >/dev/null 2>&1 || { echo 'NOT_RUN: psql is unavailable' >&2; exit 69; }
for envname in PGHOST PGDATABASE PGUSER; do
  [[ -n "${!envname:-}" ]] || { echo "REFUSED: missing $envname" >&2; exit 64; }
done
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Deliberately no -d 'postgres://...:password@...' argument.
psql -X -w -v ON_ERROR_STOP=1 -f "$source_dir/scout_photo_stage8_catalog_gate.sql"
