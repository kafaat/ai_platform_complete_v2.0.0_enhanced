# Governance Hardening Comprehensive Fix Report — 2026-07-09

## Scope

This patch continues from `governance_hardened_continued_7` and closes the remaining CI-environment fragility around v9 unit-test dependencies, after the FastAPI collection failure and the stale mirror-guard regression were addressed.

## Fixes Applied

### 1. Exact-pinned `tests_v9` unit-test requirements

Updated `tests_v9/requirements-test.txt` from mostly ranged requirements to exact direct pins. The unit CI environment now has a deterministic direct dependency surface for test collection.

Key additions/normalizations include:

- `fastapi==0.136.3`
- `pydantic[email]==2.13.4`
- `python-jose[cryptography]==3.4.0`
- `cryptography==46.0.4`
- `PyJWT==2.13.0`
- `pyotp==2.9.0`
- `PyYAML==6.0.2`
- `numpy==1.26.4`
- `nats-py==2.3.0`

### 2. Test dependency inventory and guard

Added:

- `scripts/ci/test_requirements_inventory_guard.py`
- `test_dependency_inventory.generated.json`
- `test_dependency_inventory.csv`
- `.github/workflows/test-dependency-inventory.yml`

The guard enforces:

- all direct `tests_v9/requirements-test.txt` dependencies are exact-pinned;
- known third-party imports used by `tests_v9/test_*.py` are declared in test requirements;
- generated test dependency inventory does not drift.

This prevents future `ModuleNotFoundError` fan-out during unit-test collection when a test imports an undeclared package.

### 3. Stronger unit-test dependency contract test

Replaced the previous narrow FastAPI-only test with a CI-backed contract test:

- `tests_v9/test_unit_test_environment_dependencies.py`

The test delegates to `scripts/ci/test_requirements_inventory_guard.py --check`, keeping local pytest and CI behavior aligned.

### 4. Existing PyPI-default / Alibaba-override policy preserved

Re-verified the mirror policy remains intact:

- default index remains official PyPI;
- Alibaba mirror remains an operator override;
- Tencent is blocked as a Dockerfile default;
- Dockerfile pip installs retain explicit `--timeout` and `--retries` controls.

## Verification Run

### Focused tests

```bash
pytest -q \
  services/weather-service/tests \
  services/edge-inference/tests \
  services/mcp_servers/tests \
  services/agriai-engine/tests \
  services/knowledge-graph/tests \
  services/rag-retrieval/tests \
  services/indicators-service/tests \
  tests_v9/test_unit_test_environment_dependencies.py \
  tests_v9/test_dockerfile_pip_mirror_guard.py
```

Result:

```text
35 passed, 1 skipped in 6.09s
```

### CI guards

Executed guards included:

```bash
python scripts/ci/pip_mirror_contract_guard.py
python scripts/ci/dependency_pin_guard.py
python scripts/ci/dependency_inventory_guard.py --check
python scripts/ci/service_dependency_conflict_guard.py --check
python scripts/ci/build_service_dependency_bundle.py --check
python scripts/ci/generate_service_inventory.py --check
python scripts/ci/compose_reference_guard.py
python scripts/ci/nginx_weather_edge_path_guard.py
python scripts/ci/edge_model_contract_guard.py
python scripts/ci/edge_production_readiness_guard.py
python scripts/ci/production_honesty_guard.py
python scripts/ci/test_requirements_inventory_guard.py --check
```

Results observed:

- PyPI-default + Alibaba override pip mirror contract guard passed.
- Monorepo service dependency pin guard passed.
- Dependency inventory check passed.
- Dependency conflict inventory check passed.
- Direct dependency bundle check passed.
- Compose reference guard passed.
- Nginx weather/edge path guard passed.
- Edge model contract guard passed.
- Edge production readiness guard passed.
- Production honesty guard passed.
- Test dependency inventory check passed.

Note: the long combined guard command reached the shell timeout after printing the primary guard successes; the remaining inventory checks were rerun directly and passed.

## Honest Remaining Limits

- This patch exact-pins direct test requirements; it still does not generate a resolver-backed transitive lock offline.
- Optional feature tests that use `pytest.importorskip` for heavy dependencies such as `pyarrow`, `rasterio`, `shapely`, or `pyshp` remain optional by design.
- Full repository CI should still be treated as source of truth for release gating.

## Verdict

The package now has:

```text
PyPI default + Alibaba override
Docker pip retry/timeout guard
Service direct dependency pin guard
Test direct dependency pin guard
Test import dependency inventory
Production honesty guard
Edge model provisioning truth boundary
Weather Redis/readyz hardening
```

Status:

```text
Governed runtime-real baseline + comprehensive CI dependency-environment hardening
```
