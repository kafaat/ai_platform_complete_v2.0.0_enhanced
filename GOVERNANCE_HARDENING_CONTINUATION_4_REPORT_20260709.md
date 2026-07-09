# Governance Hardening Continuation 4 — Runtime Honesty Guards

Implemented on top of `sahool_ai_platform_6bf6465_governance_hardened_continued_3`.

## Changes

1. Added `scripts/ci/production_honesty_guard.py` and CI workflow.
2. Removed misleading Edge downloader simulation/regression fallback wording.
3. Made `indicators-service` explicitly health-only/degraded instead of ready-stub.
4. Added `/capabilities`, `/contract`, and fail-closed `/v1/indicators/compute` to indicators-service.
5. Added TestClient coverage for the indicators health-only boundary.
6. Added Edge model provisioning runbook and Weather Redis integration runbook.

## Verification

- Hardened service tests pass.
- Existing governance guards pass.
- New production honesty guard passes.

## Remaining honest gaps

- Edge still requires operator-provisioned ONNX models.
- Full transitive locks require connected CI/package index.
- Redis live integration remains optional unless `WEATHER_REDIS_INTEGRATION_URL` is configured.
