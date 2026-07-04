# Backend Coverage / STAC 503 Verification — 2026-07-04

## Input

`sahool_main_cefc30e_zero_partial_102_endpoints_final_green.zip`

## Scope

This verification focused on the latest STAC/503/backfill archive and the backend-to-frontend coverage contract. It checked that core backend endpoints are not added without an explicit frontend hook/component/admin surface/internal waiver/not-ready waiver.

## Findings

- `config/endpoint_ui_coverage.json` declares 102 core endpoint coverage entries.
- `config/service_feature_ui_contracts.json` declares 26 service contracts.
- `frontend/src/config/backendCoverageRegistry.ts` has 18 advanced backend layers.
- Layer states: 16 covered, 0 partial, 1 waived_internal, 1 not_ready.
- CI wiring exists in `.github/workflows/ci.yml` for both coverage gates:
  - `python scripts/ci/service_feature_ui_contract_gate.py`
  - `python scripts/ci/endpoint_ui_coverage_gate.py`
- `tests_v9/test_coverage_gates_ci_wiring.py` guards against removing the gates from CI.

## Verification commands run

```bash
python3 scripts/ci/service_feature_ui_contract_gate.py
python3 scripts/ci/endpoint_ui_coverage_gate.py
python3 scripts/ci/endpoint_ui_coverage_gate.py --report
python3 -m pytest -q \
  tests_v9/test_endpoint_ui_coverage_gate.py \
  tests_v9/test_service_feature_ui_contract_gate.py \
  tests_v9/test_coverage_gates_ci_wiring.py

cd frontend
npm ci --legacy-peer-deps --ignore-scripts
npm audit --audit-level=moderate
npx vitest run \
  src/config/backendCoverageRegistry.test.ts \
  src/config/endpoints.test.ts \
  --no-file-parallelism --maxWorkers=1
npm run typecheck
npm run build:docker

cd services/field-segmentation
python3 -m pytest -q
```

## Results

- `service-feature-ui-contract-gate`: PASS, 26/26 services.
- `endpoint-ui-coverage-gate`: PASS, 102 core endpoints.
- Coverage gate tests: 6 passed.
- Frontend coverage config tests: 2 files / 10 tests passed.
- `npm audit --audit-level=moderate`: 0 vulnerabilities.
- `npm run typecheck`: passed.
- `npm run build:docker`: passed.
- `field-segmentation`: 29 passed.

## Remaining honest limitations

This is still static/source/build validation plus targeted tests. It does not prove live runtime behavior against Docker Compose, Playwright browser flows, real STAC provider availability, or live DB/Redis/NATS integration.

## Recommended next production gate

Run Docker Compose E2E with the real platform/raster-service path for:

1. `/api/v1/fields/{field_id}/imagery/backfill` through platform proxy.
2. `/v1/fields/{field_id}/process-from-stac` inside raster-service.
3. STAC fallback behavior under provider 503/timeouts.
4. Browser-level Playwright check that FieldView shows truthful backfill/STAC failure states without leaking internal service credentials.
