# Governance Hardening Continuation 6 — PyPI Default + Alibaba Override Fix

Date: 2026-07-09

## Scope

This patch fixes a stale guard that still enforced the older Tencent Cloud PyPI mirror decision. The repository now follows the current package-index policy:

- Official PyPI is the default package index.
- Alibaba Cloud PyPI is a supported operator/CI override.
- Dockerfile package installs must be bounded with explicit retry and timeout controls.
- Tencent mirror defaults must not be reintroduced.

## Changes

### 1. Rewrote stale Dockerfile mirror guard

Updated:

- `tests_v9/test_dockerfile_pip_mirror_guard.py`

The guard now enforces:

- `ARG PIP_INDEX_URL=https://pypi.org/simple`
- Alibaba override documented in each pip Dockerfile:
  `https://mirrors.aliyun.com/pypi/simple/`
- no stale Tencent mirror references in Dockerfiles
- every Dockerfile `pip install` line includes `--timeout` and `--retries`

### 2. Migrated Dockerfile defaults away from Tencent

Updated all pip-using Dockerfiles under:

- `services/`
- `agents/`
- `bots/`

The previous default:

```text
https://mirrors.cloud.tencent.com/pypi/simple/
```

was replaced by:

```text
https://pypi.org/simple
```

Each Dockerfile now documents Alibaba as an override:

```bash
--build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
```

### 3. Folded retry/timeout requirement into the guard

Dockerfile `pip install` commands now include explicit retry/timeout controls where missing:

```text
--timeout 300 --retries 10
```

The guard fails if new pip install lines omit those controls.

### 4. Updated mirror contract helper to PyPI-default

Updated:

- `scripts/ci/pip_mirror_env.sh`
- `.github/workflows/transitive-lock-compile-manual.yml`
- `.pip/pip-alibaba.conf`
- `docs/runbooks/ALIBABA_PYPI_MIRROR.md`
- `.env.example`
- `scripts/ci/pip_mirror_contract_guard.py`

Current behavior:

```text
Default: https://pypi.org/simple
Optional Alibaba override: https://mirrors.aliyun.com/pypi/simple/
```

### 5. Updated roadmap guard logic

Updated:

- `tests_v9/test_roadmap_phase23.py`

The historical roadmap check now matches the current decision:

- PyPI default
- Alibaba override
- no Tencent default
- retry/timeout controls present

## Verification

### Tests

```bash
pytest -q \
  services/weather-service/tests \
  services/edge-inference/tests \
  services/mcp_servers/tests \
  services/agriai-engine/tests \
  services/knowledge-graph/tests \
  services/rag-retrieval/tests \
  services/indicators-service/tests \
  tests_v9/test_dockerfile_pip_mirror_guard.py
```

Result:

```text
34 passed, 1 skipped in 2.72s
```

The skipped test is the optional live Redis integration test, which requires `WEATHER_REDIS_INTEGRATION_URL`.

### Guards

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
✓ PyPI-default + Alibaba override pip mirror contract guard passed
✓ monorepo service dependency pin guard passed
dependency_inventory_check_ok
dependency_conflict_inventory_check_ok
direct_dependency_bundle_check_ok
inventory_check_ok
✓ edge model contract guard passed
✓ edge production readiness guard passed
✓ production honesty guard passed
```

## Final state

The stale Tencent-mirror guard has been replaced. The active policy is now:

```text
Official PyPI default
+ Alibaba mirror override
+ bounded retry/timeout package installs
+ static CI guard preventing Tencent-default regression
```
