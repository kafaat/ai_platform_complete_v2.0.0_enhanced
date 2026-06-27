# Phase 16 — CI/CD Quality Gates + Supply Chain Hardening

## Objective

Convert the existing static production/release/deployment gates into a repeatable CI/CD control plane that blocks unsafe merges and unsafe release candidates before runtime deployment.

## Implemented assets

- `.github/workflows/sahool-production-gates.yml`
- `scripts/ci/validate_ci_gates.py`
- `scripts/ci/local_quality_gate.sh`
- `tests/ci/test_phase16_ci_cd_gates.py`

## Blocking jobs

The production workflow now validates:

1. Production validation gate.
2. Security audit and RLS runtime role gate.
3. Grafana/Prometheus/Alertmanager observability assets.
4. Helm/GitOps deployment readiness.
5. Release package checksums and SBOM inventory.
6. Python compile sweep.
7. Targeted security/release/deploy/observability CI contract tests.
8. Static supply-chain workflow checks.

## Security posture

The workflow is intentionally conservative:

- `permissions: contents: read` only.
- No `pull_request_target`.
- No `continue-on-error: true` for quality gates.
- No `image: latest` in workflow jobs.
- All gate scripts are local and versioned with the repository.
- Local CI gate mirrors the GitHub workflow for pre-push validation.

## Local execution

```bash
./scripts/ci/local_quality_gate.sh
```

## Result

Phase 16 makes release quality reproducible. The release candidate can now be checked in CI with the same gates used locally before a Docker/Helm/Kubernetes deployment.
