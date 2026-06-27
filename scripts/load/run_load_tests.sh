#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://localhost}"
FIELD_ID="${FIELD_ID:-}"
TENANT_ID="${TENANT_ID:-}"
SAHOOL_JWT="${SAHOOL_JWT:-}"
INDEX="${INDEX:-ndvi}"
IMAGERY_DATE="${IMAGERY_DATE:-latest}"

if ! command -v k6 >/dev/null 2>&1; then
  echo "k6 is required for load tests. Install k6 and retry." >&2
  exit 127
fi
if [[ -z "$FIELD_ID" || -z "$TENANT_ID" ]]; then
  echo "FIELD_ID and TENANT_ID are required." >&2
  exit 2
fi

export BASE_URL FIELD_ID TENANT_ID SAHOOL_JWT INDEX IMAGERY_DATE
k6 run "$(dirname "$0")/k6_field_imagery_ai.js"
