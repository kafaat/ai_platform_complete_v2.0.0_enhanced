# AI Container Review and Fix Report — 2026-07-09

## Scope

Reviewed AI-oriented containers after P0/P1/P2 decomposition and container-fleet hardening:

- `services/ai_agronomist`
- `services/agriai-engine`
- `services/local-ai-rag`
- `services/rag-retrieval`
- `services/knowledge-graph`
- `services/supervisor-agent`
- `services/guardrails-engine`
- `services/edge-inference`
- `services/sam2-inference`

## Fixes applied

### 1. Docker Compose liveness corrected

The following Compose healthchecks were using `/readyz` as Docker liveness even though readiness can legitimately fail because of model/upstream/vector-store dependencies:

- `sahool-rag-retrieval`
- `sahool-knowledge-graph`
- `sahool-ai-agronomist`
- `sahool-supervisor-agent`
- `sahool-guardrails-engine`
- `sahool-sam2-inference`

They now use `/healthz` for container liveness. Readiness remains available through `/readyz` and should be checked by deployment/readiness gates, not Docker's restart loop.

### 2. Requirements inline comment parsing hardened

Fixed malformed inline comments that could be parsed inconsistently by pip tooling:

- `services/auth/requirements.txt`
- `services/local-ai-rag/requirements.txt`

Examples corrected from `package==x.y.z# comment` to `package==x.y.z  # comment`.

### 3. AI container contract guard added

Added:

- `scripts/ci/ai_container_contract_guard.py`
- `tests_v9/test_ai_container_contract_guard.py`
- `.github/workflows/ai-container-contract.yml`
- `ai_container_audit.generated.json`
- `ai_container_audit.csv`

The guard enforces:

- AI Dockerfile healthchecks use `/healthz`, not `/readyz`.
- AI Compose healthchecks use `/healthz`, not `/readyz`.
- pip install commands include `--timeout 300 --retries 10`.
- post-decomposition copy contracts are preserved for `ai_agronomist`, `edge-inference`, `sam2-inference`, `rag-retrieval`, and `knowledge-graph`.
- known malformed requirements inline comments do not return.

### 4. Runtime smoke updated

`scripts/ci/runtime_real_smoke.sh` now includes:

- `indicators_container_contract_guard.py`
- `vegetation_container_contract_guard.py`
- `container_fleet_contract_guard.py`
- `ai_container_contract_guard.py --check`

and the corresponding pytest contract tests.

## Verification

Executed successfully:

```bash
python -m py_compile scripts/ci/ai_container_contract_guard.py tests_v9/test_ai_container_contract_guard.py
python scripts/ci/ai_container_contract_guard.py --check
pytest -q tests_v9/test_ai_container_contract_guard.py
python scripts/ci/container_fleet_contract_guard.py
python scripts/ci/pip_audit_resolution_guard.py
python scripts/ci/dependency_inventory_guard.py --check
python scripts/ci/service_dependency_conflict_guard.py --check
python scripts/ci/build_service_dependency_bundle.py --check
python scripts/ci/test_requirements_inventory_guard.py --check
python scripts/ci/route_mount_contract_guard.py --check
python scripts/ci/generate_service_inventory.py --check
```

Targeted AI tests passed:

```text
12 passed, 2 skipped
21 passed
```

The skipped tests are service-level tests with unavailable optional runtime imports in the local chat sandbox, not AI container contract failures.

## Final judgment

AI containers are now more consistent after decomposition:

- liveness is separated from readiness;
- known runtime copy contracts are guarded;
- malformed requirement comments are fixed;
- container-level regressions are protected by a dedicated CI guard.

This does not replace Docker build matrix validation in real CI. Production Certification still requires Docker build evidence and the existing P-CERT evidence pack.
