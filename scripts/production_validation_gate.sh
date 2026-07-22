#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"

echo "== SAHOOL production validation gate =="

echo "-- security audit --"
bash scripts/security_audit.sh

echo "-- RLS runtime role gate --"
python scripts/security/rls_runtime_gate.py

echo "-- compose parse --"
python - <<'PY'
import yaml
from pathlib import Path
compose = yaml.safe_load(Path('docker-compose.v9.yml').read_text(encoding='utf-8'))
services = compose.get('services', {})
assert 'sahool-platform' in services, 'sahool-platform missing'
assert 'sahool-nginx' in services, 'sahool-nginx missing'
print(f"OK: docker-compose.v9.yml parsed; services={len(services)}")
PY

echo "-- migration manifest required runtime migrations --"
python - <<'PY'
from pathlib import Path
manifest = Path('migrations/MANIFEST.txt').read_text(encoding='utf-8')
required = [
    'v106_phase9_10_runtime_strengthening.sql',
    'v107_phase9_10_event_drift_hardening.sql',
    'v108_phase10_feature_store_model_registry_runtime.sql',
    'v109_phase9_iot_execution_adapters.sql',
    'v110_phase12_plugin_sandbox_runtime.sql',
    'v111_phase11_federated_agent_runtime.sql',
    'v112_mobile_offline_sync_runtime.sql',
    'v113_phase_runtime_workers_jobs.sql',
]
missing = [item for item in required if item not in manifest]
assert not missing, f'missing required runtime migrations: {missing}'
print(f"OK: required runtime migrations present={len(required)}")
PY


echo "-- migration manifest consistency --"
python scripts/migrations/validate_migration_manifest.py --root .
python scripts/security/validate_rls_write_policies.py --root .


echo "-- legacy runtime path quarantine audit --"
python scripts/architecture/legacy_path_audit.py --root . --strict

echo "-- source-of-truth audit --"
python scripts/architecture/source_of_truth_audit.py --root . --strict

echo "-- container image pinning --"
python scripts/ci/container_image_pin_guard.py

echo "-- certification matrix validation --"
python scripts/certification/validate_certification_matrix.py --root .

echo "-- Python compile sweep --"
python - <<'PY'
import py_compile
from pathlib import Path
skip = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache'}
compiled = failed = 0
for path in Path('.').rglob('*.py'):
    if any(part in skip for part in path.parts):
        continue
    try:
        py_compile.compile(str(path), doraise=True)
        compiled += 1
    except Exception as exc:
        failed += 1
        print(f"FAIL: {path}: {exc}")
if failed:
    raise SystemExit(1)
print(f"OK: Python compile compiled={compiled} failed=0")
PY

echo "OK: production validation gate passed"
