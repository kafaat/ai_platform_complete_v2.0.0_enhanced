#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost}"
need(){ command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 2; }; }
need curl
check(){
  local name="$1"; local path="$2"
  local url="${BASE_URL%/}${path}"
  local code
  code=$(curl -sk -o /tmp/sahool_obs_body -w '%{http_code}' "$url" || true)
  if [[ "$code" != 2* ]]; then
    echo "FAIL $name $url status=$code" >&2
    head -c 500 /tmp/sahool_obs_body >&2 || true
    exit 1
  fi
  echo "OK $name $path"
}
check platform_ready /readyz
check raster_ready /api/raster/readyz
check rag_ready /api/rag/readyz
check kg_ready /api/knowledge-graph/readyz
check ai_ready /api/ai-agronomist/readyz
check ai_metrics /api/ai-agronomist/metrics
check rag_metrics /api/rag/metrics
check kg_metrics /api/knowledge-graph/metrics
