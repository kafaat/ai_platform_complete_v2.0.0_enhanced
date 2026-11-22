#!/usr/bin/env bash
# Readiness and metrics smoke through the v9 gateway.
#   BASE_URL=http://localhost SAHOOL_JWT=<access token> ./scripts/observability_smoke.sh
# Every service alias below sits behind the gateway identity check (auth_request), so a
# probe without a token measures the 401, never the service. /readyz itself is private-
# network only (run this from the gateway host or its network).
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost}"
need(){ command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 2; }; }
need curl
if [[ -z "${SAHOOL_JWT:-}" ]]; then
  echo "SAHOOL_JWT is required: the service aliases are behind the gateway identity check" >&2
  exit 2
fi
BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT
fail(){
  echo "FAIL $1 $2 $3" >&2
  head -c 500 "$BODY" >&2 || true
  exit 1
}
# check <name> <path> <json|prometheus>: 2xx is not enough, the answer must be the named
# endpoint's own (a gateway fallback or the SPA shell answering 200 is a failure).
check(){
  local name="$1"; local path="$2"; local kind="$3"
  local url="${BASE_URL%/}${path}"
  local out code ctype
  out=$(curl -sk -o "$BODY" -w '%{http_code} %{content_type}' \
    -H "Authorization: Bearer ${SAHOOL_JWT}" "$url" || true)
  code="${out%% *}"; ctype="${out#* }"
  [[ "$code" == 2* ]] || fail "$name" "$url" "status=$code"
  case "$kind" in
    json)
      [[ "$ctype" == application/json* ]] || fail "$name" "$url" "content_type=${ctype:-none} expected=application/json"
      ;;
    prometheus)
      [[ "$ctype" == text/plain* ]] || fail "$name" "$url" "content_type=${ctype:-none} expected=text/plain"
      grep -q '^# TYPE ' "$BODY" || fail "$name" "$url" "body has no Prometheus '# TYPE' line"
      ;;
    *) echo "unknown check kind: $kind" >&2; exit 2 ;;
  esac
  echo "OK $name $path"
}
check platform_ready /readyz json
check raster_ready /api/raster/readyz json
check rag_ready /api/rag/readyz json
check kg_ready /api/knowledge-graph/readyz json
check ai_ready /api/ai-agronomist/readyz json
check ai_metrics /api/ai-agronomist/metrics prometheus
check rag_metrics /api/rag/metrics prometheus
check kg_metrics /api/knowledge-graph/metrics prometheus
