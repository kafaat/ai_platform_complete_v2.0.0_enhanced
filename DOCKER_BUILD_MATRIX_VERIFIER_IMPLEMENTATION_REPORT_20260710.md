# Docker Build Matrix Verifier Implementation Report — 2026-07-10

## Scope

Implemented the extended Docker build checklist and a CI-ready verifier for the release-sensitive Sahool services:

- `raster-service`
- `weather-service`
- `edge-inference`
- `sam2-inference`
- `auth`
- `sahool-platform`
- `odoo-bridge`

The implementation also supports `--all` mode for every Dockerfile-backed service discovered under `services/`.

## Files Added

- `docs/runbooks/DOCKER_BUILD_CHECKLIST_CRITICAL_AND_EXTENDED_SERVICES_20260710.md`
- `scripts/ci/docker_build_matrix_verifier.py`
- `tests_v9/test_docker_build_matrix_verifier_static.py`
- `.github/workflows/docker-build-matrix-verifier.yml`

## Important Corrections Applied

The user-provided draft was converted into repository-accurate implementation details:

1. `edge-inference` currently uses `services/edge-inference/Dockerfile.arm64`, not `services/edge-inference/Dockerfile`.
2. `sam2-inference` exposes port `8080` in its Dockerfile.
3. `raster-service` exposes port `8001`.
4. `odoo-bridge` exposes port `8126`.
5. The verifier never marks `production_certified=true`; it only records evidence. Certification remains a separate release decision.
6. Model provisioning is not inferred from `/healthz`; strict artifact-present readiness must be run separately for P-CERT-4.
7. The verifier supports `--critical`, `--extended`, explicit `--services`, and `--all` modes.

## Evidence Behavior

When executed with `--write`, the verifier writes:

- `certification/evidence/docker_build_matrix_full.json`
- `certification/evidence/ci_summary.json`
- `certification/evidence/model_provisioning_summary.json`

These files are generated only from phases actually run. Skipped phases are recorded as skipped, not as pass.

## Verification Performed in This Environment

Docker was not executed in this chat environment. The following static checks were run:

```bash
python -m py_compile scripts/ci/docker_build_matrix_verifier.py
pytest -q tests_v9/test_docker_build_matrix_verifier_static.py
```

Result:

```text
4 passed
```

Additional guard checks run after updating the report index:

```bash
python scripts/ci/report_index_guard.py --write
python scripts/ci/report_index_guard.py --check
pytest -q tests_v9/test_docker_build_matrix_verifier_static.py tests_v9/test_report_index_guard.py
```

## Production Certification Impact

This change prepares evidence collection for:

- `P-CERT-1` Docker build matrix evidence.
- `P-CERT-4` model-readiness evidence for `edge-inference` and `sam2-inference`.

It does not close those blockers until the workflow is executed in CI with Docker and required model artifacts.
