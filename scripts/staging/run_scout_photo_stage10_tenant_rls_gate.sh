#!/usr/bin/env bash
set -Eeuo pipefail
# Will ONLY run against explicit staging with two existing image fixtures.
# No test rows are inserted; all database statements are read-only.
if [[ "${SCOUT_ACCEPTANCE_ENV:-}" != staging ]]; then
  echo 'REFUSED: SCOUT_ACCEPTANCE_ENV=staging required' >&2
  exit 64
fi
if ! command -v psql >/dev/null 2>&1; then
  echo 'NOT_RUN: psql unavailable, staging RLS proof remains OPEN' >&2
  exit 69
fi
for key in PGHOST PGDATABASE PGUSER SCOUT_EXPECTED_STAGING_DB SCOUT_STAGE10_FIXTURE_TENANT_A SCOUT_STAGE10_FIXTURE_TENANT_B; do
  if [[ -z "${!key:-}" ]]; then
    echo "REFUSED: missing $key; staging RLS not tested" >&2
    exit 64
  fi
done
if [[ "$PGDATABASE" != "$SCOUT_EXPECTED_STAGING_DB" ]]; then
  echo 'REFUSED: database identity differs from explicitly expected staging DB' >&2
  exit 64
fi
uuid_pattern='^[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$'
if [[ ! "$SCOUT_STAGE10_FIXTURE_TENANT_A" =~ $uuid_pattern || ! "$SCOUT_STAGE10_FIXTURE_TENANT_B" =~ $uuid_pattern || "${SCOUT_STAGE10_FIXTURE_TENANT_A,,}" == "${SCOUT_STAGE10_FIXTURE_TENANT_B,,}" ]]; then
  echo 'REFUSED: two distinct canonical UUID staging fixtures required' >&2
  exit 64
fi
scriptdir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# psql -w never prompts. stdout is non-secret and must not claim live data was
# written. --set values are UUID syntax validated above, with quoted SQL usage.
PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-5}" psql -X -w -v ON_ERROR_STOP=1 \
  -v fixture_tenant_a="$SCOUT_STAGE10_FIXTURE_TENANT_A" \
  -v fixture_tenant_b="$SCOUT_STAGE10_FIXTURE_TENANT_B" \
  -f "$scriptdir/scout_photo_stage10_tenant_rls_gate.sql"
