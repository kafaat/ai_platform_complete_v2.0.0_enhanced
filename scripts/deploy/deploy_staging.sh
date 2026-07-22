#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
bash scripts/production_validation_gate.sh
python scripts/deploy/validate_helm_readiness.py --env staging
helm upgrade --install sahool ./helm/sahool   --namespace sahool-staging   --create-namespace   -f helm/sahool/values.yaml   -f helm/sahool/values-staging.yaml
