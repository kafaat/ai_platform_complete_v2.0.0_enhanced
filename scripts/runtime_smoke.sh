#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost}"
AUTH_HEADER=()
if [[ -n "${SAHOOL_JWT:-}" ]]; then
  AUTH_HEADER=(-H "Authorization: Bearer ${SAHOOL_JWT}")
fi
probe() {
  local label="$1"; shift
  local url="$1"; shift
  echo "==> ${label}: ${url}"
  curl -fsS --max-time "${CURL_TIMEOUT:-10}" "${AUTH_HEADER[@]}" "$url" >/tmp/sahool_probe.json
  python - <<'PY'
import json
from pathlib import Path
p=Path('/tmp/sahool_probe.json')
try:
    data=json.loads(p.read_text(encoding="utf-8"))
    print(data if len(str(data)) < 500 else str(data)[:500])
except Exception:
    print(p.read_text(encoding="utf-8")[:500])
PY
}
probe "nginx" "${BASE_URL}/healthz"
probe "raster" "${BASE_URL}/api/raster/healthz"
probe "rag" "${BASE_URL}/api/rag/healthz"
probe "knowledge-graph" "${BASE_URL}/api/knowledge-graph/healthz"
probe "ai-agronomist" "${BASE_URL}/api/ai-agronomist/healthz"
probe "guardrails" "${BASE_URL}/api/guardrails/healthz"
echo "runtime smoke completed"
