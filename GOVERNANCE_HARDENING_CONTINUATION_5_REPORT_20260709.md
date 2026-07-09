# Governance Hardening Continuation 5 — Alibaba PyPI Mirror Contract

Date: 2026-07-09
Package lineage: `sahool_ai_platform_6bf6465_governance_hardened_continued_4.zip` -> `continued_5`

## Objective
Add an Alibaba Cloud PyPI mirror path for connected CI dependency lock compilation without falsely claiming that transitive locks were compiled offline.

## Implemented changes

### 1. Mirror-aware pip environment helper
Added:

- `scripts/ci/pip_mirror_env.sh`
- `.pip/pip-alibaba.conf`

Default mirror:

```text
https://mirrors.aliyun.com/pypi/simple/
```

The helper exports:

- `PYPI_MIRROR_URL`
- `PIP_INDEX_URL`
- `PIP_TRUSTED_HOST`
- `PIP_DEFAULT_TIMEOUT`
- `PIP_RETRIES`

Operators can override the mirror with `PYPI_MIRROR_URL` or `PIP_INDEX_URL`.

### 2. Transitive lock compiler now uses configured mirror
Updated:

- `scripts/ci/compile_transitive_service_locks.sh`
- `.github/workflows/transitive-lock-compile-manual.yml`

The compiler now sources `scripts/ci/pip_mirror_env.sh` and passes `--index-url "$PIP_INDEX_URL"` to `piptools compile`.

### 3. Mirror contract guard
Added:

- `scripts/ci/pip_mirror_contract_guard.py`
- `.github/workflows/pip-mirror-contract.yml`

The guard validates:

- Alibaba mirror URL is present.
- Mirror is operator-overridable.
- No embedded credentials are present in mirror URLs.
- `compile_transitive_service_locks.sh` sources the shared mirror helper.
- `pip-compile` uses the configured `PIP_INDEX_URL`.

### 4. Documentation
Added:

- `docs/runbooks/ALIBABA_PYPI_MIRROR.md`

Updated:

- `.env.example`

The runbook documents the default Alibaba mirror, private mirror override, and the offline limitation.

## Verification

Executed tests:

```bash
pytest -q \
  services/weather-service/tests \
  services/edge-inference/tests \
  services/mcp_servers/tests \
  services/agriai-engine/tests \
  services/knowledge-graph/tests \
  services/rag-retrieval/tests \
  services/indicators-service/tests
```

Result:

```text
33 passed, 1 skipped in 2.48s
```

Executed guards:

```bash
python scripts/ci/pip_mirror_contract_guard.py
python scripts/ci/dependency_pin_guard.py
python scripts/ci/dependency_inventory_guard.py --check
python scripts/ci/service_dependency_conflict_guard.py --check
python scripts/ci/build_service_dependency_bundle.py --check
python scripts/ci/generate_service_inventory.py --check
python scripts/ci/edge_model_contract_guard.py
python scripts/ci/edge_production_readiness_guard.py
python scripts/ci/production_honesty_guard.py
```

Result:

```text
✓ Alibaba PyPI mirror contract guard passed
✓ monorepo service dependency pin guard passed
dependency_inventory_check_ok
dependency_conflict_inventory_check_ok
direct_dependency_bundle_check_ok
✓ edge model contract guard passed
✓ edge production readiness guard passed
✓ production honesty guard passed
```

## Honest remaining limitations

- Transitive lock files still require connected CI or an internal mirror; they were not generated offline in this environment.
- Alibaba mirror is configured as the default for the lock compiler, not forced globally on every developer environment.
- Credentials must not be embedded in mirror URLs; private mirror auth should use CI secrets, `.netrc`, keyring, or runner-level configuration.
