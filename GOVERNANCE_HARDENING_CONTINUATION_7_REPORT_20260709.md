# Governance Hardening Continuation 7 — Unit Test FastAPI Dependency Closure

Date: 2026-07-09

## Issue

The v9 unit CI job failed with `ModuleNotFoundError: No module named 'fastapi'` while collecting/running `tests_v9/test_e2e_cdse_to_element84_switch_v31_4.py`.

The failure was a CI environment dependency gap, not an Element84/CDSE product logic bug. The unit job installs `tests_v9/requirements-test.txt`, so any third-party package imported directly by `tests_v9` must be declared there.

## Fixes Applied

### 1. Test dependency declaration

Updated:

- `tests_v9/requirements-test.txt`

Added:

```txt
fastapi==0.136.3
```

This keeps the unit collection environment independent from service container images or developer-local Python environments.

### 2. Regression guard

Added:

- `tests_v9/test_unit_test_environment_dependencies.py`

The guard scans `tests_v9/test_*.py` for tracked third-party imports and fails if required packages are missing from `tests_v9/requirements-test.txt`.

Current tracked dependency:

- `fastapi` -> `fastapi`

## Verification

Executed:

```bash
pytest -q tests_v9/test_unit_test_environment_dependencies.py tests_v9/test_dockerfile_pip_mirror_guard.py
python scripts/ci/pip_mirror_contract_guard.py
python scripts/ci/dependency_pin_guard.py
python scripts/ci/dependency_inventory_guard.py --check
python scripts/ci/production_honesty_guard.py
```

Results:

```txt
2 passed
✓ PyPI-default + Alibaba override pip mirror contract guard passed
✓ monorepo service dependency pin guard passed
dependency_inventory_check_ok
✓ production honesty guard passed
```

## Policy Confirmed

- Default package index remains official PyPI.
- Alibaba remains an operator override.
- Tencent must not return as default.
- Dockerfile pip installs remain protected by retry/timeout guards.
- Unit tests must declare direct third-party imports in `tests_v9/requirements-test.txt`.

## Remaining Notes

The failing file referenced by CI was not present in this extracted package snapshot, but the dependency closure is applied at the unit-test environment level, which is the correct root-cause fix for main.
