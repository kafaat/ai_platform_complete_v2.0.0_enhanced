#!/usr/bin/env bash
set -euo pipefail

# Fast non-destructive runtime-real smoke profile.
# This does not replace full CI or live deployment certification. It verifies
# the contracts that should fail quickly before a merge.

PYTHON_BIN="${PYTHON_BIN:-python}"

echo "[runtime-smoke] static/runtime contract guards"
"$PYTHON_BIN" scripts/ci/production_honesty_guard.py
"$PYTHON_BIN" scripts/ci/internal_graphql_security_guard.py
"$PYTHON_BIN" scripts/ci/health_readiness_schema_guard.py --check
"$PYTHON_BIN" scripts/ci/contract_capabilities_schema_guard.py --check
"$PYTHON_BIN" scripts/ci/route_mount_contract_guard.py --check
"$PYTHON_BIN" scripts/ci/route_residual_classification_guard.py --check
"$PYTHON_BIN" scripts/ci/production_evidence_pack_guard.py --check
"$PYTHON_BIN" scripts/ci/production_certification_checklist_guard.py --check
"$PYTHON_BIN" scripts/ci/edge_model_contract_guard.py
"$PYTHON_BIN" scripts/ci/edge_production_readiness_guard.py
"$PYTHON_BIN" scripts/ci/indicators_container_contract_guard.py
"$PYTHON_BIN" scripts/ci/vegetation_container_contract_guard.py
"$PYTHON_BIN" scripts/ci/container_fleet_contract_guard.py
"$PYTHON_BIN" scripts/ci/ai_container_contract_guard.py --check
"$PYTHON_BIN" scripts/ci/pip_audit_resolution_guard.py
"$PYTHON_BIN" scripts/ci/raw_data_processing_contract_guard.py
"$PYTHON_BIN" scripts/ci/raw_weather_processing_contract_guard.py

if command -v pytest >/dev/null 2>&1; then
  echo "[runtime-smoke] targeted pytest contracts"
  pytest -q \
    services/weather-service/tests \
    services/edge-inference/tests \
    tests_v9/test_internal_graphql_security_guard.py \
    tests_v9/test_health_readiness_schema_guard.py \
    tests_v9/test_contract_capabilities_schema_guard.py \
    tests_v9/test_route_residual_classification_guard.py \
    tests_v9/test_production_evidence_pack_guard.py \
    tests_v9/test_indicators_container_contract_guard.py \
    tests_v9/test_vegetation_container_contract_guard.py \
    tests_v9/test_container_fleet_contract_guard.py tests_v9/test_runtime_container_deep_contract_guard.py \
    tests_v9/test_ai_container_contract_guard.py \
    tests_v9/test_raw_data_processing_contract_guard.py
else
  echo "[runtime-smoke] pytest not installed; skipped targeted pytest contracts" >&2
fi

echo "runtime_real_smoke_ok"

python scripts/ci/raster_pixel_qa_indicator_guard.py
python scripts/ci/raster_topographic_qa_guard.py
python scripts/ci/raster_validated_product_guard.py
