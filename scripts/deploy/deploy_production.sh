#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
bash scripts/production_validation_gate.sh
python scripts/observability/validate_observability_assets.py
python scripts/deploy/validate_helm_readiness.py --env production
python scripts/release/validate_release_package.py
helm upgrade --install sahool ./helm/sahool   --namespace sahool   --create-namespace   -f helm/sahool/values.yaml   -f helm/sahool/values-production.yaml   --atomic   --timeout 15m
