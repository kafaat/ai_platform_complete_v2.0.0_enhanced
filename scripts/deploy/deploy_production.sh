#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
bash scripts/production_validation_gate.sh
python scripts/observability/validate_observability_assets.py
python scripts/deploy/validate_helm_readiness.py --env production
python scripts/release/validate_release_package.py
helm upgrade --install sahool ./helm/sahool   --namespace sahool   --create-namespace   -f helm/sahool/values.yaml   -f helm/sahool/values-production.yaml   --atomic   --timeout 15m
# The chart does not deploy services/auth yet (deploy-3, W3-09). The gateway starts
# without it but fails every verified route closed until the Service exists; say so.
AUTH_SERVICE="$(python - <<'PY'
import yaml
base = yaml.safe_load(open("helm/sahool/values.yaml", encoding="utf-8"))
prod = yaml.safe_load(open("helm/sahool/values-production.yaml", encoding="utf-8")) or {}
override = ((prod.get("gateway") or {}).get("auth") or {}).get("serviceName")
print(override or base["gateway"]["auth"]["serviceName"])
PY
)"
if ! kubectl --namespace sahool get service "$AUTH_SERVICE" >/dev/null 2>&1; then
  echo "WARNING: Service $AUTH_SERVICE is missing in namespace sahool: every gateway route that needs auth_request answers 500 (fail closed) until services/auth is deployed (W3-09)." >&2
fi
