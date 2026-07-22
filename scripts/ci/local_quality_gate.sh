#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$ROOT_DIR"

echo "== Sahool local CI quality gate =="

python3 scripts/ci/validate_ci_gates.py --root .
python3 scripts/ci/github_actions_policy_guard.py
python3 scripts/ci/local_test_dependency_preflight.py
bash scripts/ci/raster_quality_gate.sh
bash scripts/production_validation_gate.sh
bash scripts/security_audit.sh
python3 scripts/security/rls_runtime_gate.py --root .
python3 scripts/observability/validate_observability_assets.py --root .
python3 scripts/deploy/validate_helm_readiness.py --env production
python3 scripts/release/validate_release_package.py --root .
python3 scripts/migrations/validate_migration_manifest.py --root .
python3 scripts/security/validate_rls_write_policies.py --root .

python3 scripts/architecture/legacy_path_audit.py --root . --strict
python3 scripts/architecture/source_of_truth_audit.py --root . --strict
python3 scripts/certification/validate_certification_matrix.py --root .

echo "== Python compile sweep =="
python3 - <<'PY'
from __future__ import annotations
import py_compile
from pathlib import Path
skip = {'.git', '.pytest_cache', '__pycache__', 'node_modules', '.venv', 'venv', 'build', 'dist'}
compiled = 0
failed = []
for path in sorted(Path('.').rglob('*.py')):
    if any(part in skip for part in path.parts):
        continue
    try:
        py_compile.compile(str(path), doraise=True)
        compiled += 1
    except Exception as exc:  # pragma: no cover - diagnostic script
        failed.append((str(path), str(exc)))
print(f"compiled={compiled} failed={len(failed)}")
if failed:
    for path, exc in failed:
        print(f"{path}: {exc}")
    raise SystemExit(1)
PY

echo "== Targeted contract tests =="
python3 -m pytest -q \
  tests/ci/test_phase16_ci_cd_gates.py \
  tests/deploy/test_phase15_deployment_readiness_contracts.py \
  tests/release/test_phase14_release_packaging_contracts.py \
  tests/observability/test_phase13_observability_assets.py \
  tests/security/test_phase12_final_production_gates.py \
  tests/architecture/test_phase21_legacy_quarantine.py \
  tests/architecture/test_phase21_source_of_truth.py \
  tests/certification/test_phase21_certification_matrix.py

echo "Sahool local CI quality gate passed"
