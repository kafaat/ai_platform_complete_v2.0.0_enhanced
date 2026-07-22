#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://localhost}"
SAHOOL_JWT="${SAHOOL_JWT:-}"
FIELD_ID="${FIELD_ID:-}"
TENANT_ID="${TENANT_ID:-}"
INDEX="${INDEX:-ndvi}"
DATE="${IMAGERY_DATE:-latest}"

need_ok() {
  local name="$1" url="$2"
  local code
  code=$(curl -sS -o /tmp/sahool_recovery_body -w "%{http_code}" "$url" || true)
  if [[ "$code" =~ ^2|3 ]]; then
    echo "[ok] $name $code"
    return 0
  fi
  echo "[fail] $name $code: $(cat /tmp/sahool_recovery_body 2>/dev/null | head -c 300)" >&2
  return 1
}

need_ok "gateway raster" "$BASE_URL/api/raster/healthz"
need_ok "gateway rag" "$BASE_URL/api/rag/healthz"
need_ok "gateway knowledge-graph" "$BASE_URL/api/knowledge-graph/healthz"
need_ok "gateway ai-agronomist" "$BASE_URL/api/ai-agronomist/healthz"

if [[ -n "$FIELD_ID" ]]; then
  need_ok "available dates" "$BASE_URL/api/raster/v1/fields/$FIELD_ID/available-dates" || true
  need_ok "tilejson versioned" "$BASE_URL/api/raster/v1/fields/$FIELD_ID/tilejson?index=$INDEX&date=$DATE&v=recovery" || true
fi

if [[ -n "$SAHOOL_JWT" ]]; then
  BASE_URL="$BASE_URL" SAHOOL_JWT="$SAHOOL_JWT" bash scripts/outbox_reliability_check.sh || true
fi

echo "Recovery smoke completed."
