#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://localhost}"
SAHOOL_JWT="${SAHOOL_JWT:-}"
FIELD_ID="${FIELD_ID:-}"
TENANT_ID="${TENANT_ID:-}"
INDEX="${INDEX:-ndvi}"
DATE="${IMAGERY_DATE:-latest}"
RESPONSE_FILE=$(mktemp "${TMPDIR:-/tmp}/sahool_recovery.XXXXXXXX")
trap 'rm -f "$RESPONSE_FILE"' EXIT
CURL_HEADERS=()
if [[ -n "$SAHOOL_JWT" ]]; then
  CURL_HEADERS=(-H "Authorization: Bearer $SAHOOL_JWT")
fi

need_ok() {
  local name="$1" url="$2"
  local code
  if ! code=$(curl -sS -o "$RESPONSE_FILE" -w "%{http_code}" "${CURL_HEADERS[@]}" "$url"); then
    echo "[fail] $name transport error" >&2
    return 1
  fi
  if [[ "$code" =~ ^2[0-9][0-9]$ ]]; then
    echo "[ok] $name $code"
    return 0
  fi
  echo "[fail] $name $code: $(head -c 300 "$RESPONSE_FILE")" >&2
  return 1
}

need_ok "gateway raster" "$BASE_URL/api/raster/healthz"
need_ok "gateway rag" "$BASE_URL/api/rag/healthz"
need_ok "gateway knowledge-graph" "$BASE_URL/api/knowledge-graph/healthz"
need_ok "gateway ai-agronomist" "$BASE_URL/api/ai-agronomist/healthz"

if [[ -n "$FIELD_ID" ]]; then
  need_ok "available dates" "$BASE_URL/api/raster/v1/fields/$FIELD_ID/available-dates"
  need_ok "tilejson versioned" "$BASE_URL/api/raster/v1/fields/$FIELD_ID/tilejson?index=$INDEX&date=$DATE&v=recovery"
fi

if [[ -n "$SAHOOL_JWT" ]]; then
  BASE_URL="$BASE_URL" SAHOOL_JWT="$SAHOOL_JWT" bash scripts/outbox_reliability_check.sh
fi

echo "Recovery smoke completed (requested HTTP checks only; not a T7 restore or RTO/RPO certificate)."
