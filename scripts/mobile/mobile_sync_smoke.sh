#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost}"
: "${SAHOOL_JWT:?SAHOOL_JWT is required}"
curl_json() {
  curl -fsS -H "Authorization: Bearer ${SAHOOL_JWT}" -H "Accept: application/json" "$@"
}

echo "[mobile-sync] manifest"
curl_json "${BASE_URL}/api/v1/sync/manifest" | grep -q "stable_operation_id"

echo "[mobile-sync] status"
curl_json "${BASE_URL}/api/v1/sync/status" | grep -q "queue"

echo "[mobile-sync] deterministic retry contract"
OP_ID="${OP_ID:-00000000-0000-7000-8000-000000000112}"
payload="{\"tenant_id\":\"${TENANT_ID}\",\"operations\":[{\"op_id\":\"${OP_ID}\",\"kind\":\"observation_create\",\"payload\":{\"source\":\"mobile_sync_smoke\"}}]}"
first=$(curl -fsS -X POST "${BASE_URL}/api/v1/sync" \
  -H "Authorization: Bearer ${SAHOOL_JWT}" -H "Content-Type: application/json" \
  -d "$payload")
second=$(curl -fsS -X POST "${BASE_URL}/api/v1/sync" \
  -H "Authorization: Bearer ${SAHOOL_JWT}" -H "Content-Type: application/json" \
  -d "$payload")

echo "$first" | grep -q "$OP_ID"
echo "$second" | grep -q "$OP_ID"
echo "[mobile-sync] OK"
