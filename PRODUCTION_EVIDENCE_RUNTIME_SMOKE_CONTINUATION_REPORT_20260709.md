# Production Evidence + Runtime Smoke Continuation Report — 2026-07-09

## Scope

Implemented non-breaking certification discipline on top of the corrected post-P2 release candidate.

## Added artifacts

- `certification/evidence/production_evidence_manifest.generated.json`
- `certification/evidence/ci_summary.json`
- `certification/evidence/transitive_locks_summary.json`
- `certification/evidence/model_provisioning_summary.json`
- `certification/evidence/redis_live_test_summary.json`
- `certification/evidence/guard_results_summary.json`
- `docs/runbooks/PRODUCTION_EVIDENCE_PACK.md`
- `scripts/ci/production_evidence_pack_guard.py`
- `.github/workflows/production-evidence-pack.yml`

## Evidence policy

The repository remains `release_candidate_not_production_certified` until real evidence is attached and verified for every non-waivable blocker.

Non-waivable blockers:

- `P-CERT-1` — Full branch CI
- `P-CERT-2` — Connected transitive lock generation
- `P-CERT-4` — ONNX/SAM2 model provisioning
- `GUARDS` — guard results summary

Redis live integration (`P-CERT-3`) is the only waivable blocker, and only with a documented reason when Redis is not used for correctness/state.

## Added runtime smoke profile

- `scripts/ci/runtime_real_smoke.sh`
- `.github/workflows/runtime-real-smoke.yml`
- `tests_v9/test_runtime_real_smoke_script.py`

The smoke profile checks:

- production honesty
- internal route / GraphQL security
- health/readiness schema
- contract/capabilities schema
- route mount inventory
- route residual classification
- production evidence pack
- production certification checklist
- edge model contract
- edge production readiness
- targeted weather/edge/schema tests

## Added residual route classification

- `scripts/ci/route_residual_classification_guard.py`
- `route_residual_classification.generated.json`
- `route_residual_classification.csv`
- `route_residual_business_allowlist.generated.json`
- `tests_v9/test_route_residual_classification_guard.py`
- `.github/workflows/route-residual-classification.yml`

Residual `main.py` routes are now classified as:

- `health`
- `readiness`
- `metrics`
- `internal_endpoint`
- `contract`
- `capabilities`
- `legacy_alias`
- `business_endpoint`

Business endpoints in `main.py` are frozen in an allowlist. New business endpoints in `main.py` require explicit review.

## Added report hygiene

- `REPORT_INDEX.md`
- `scripts/ci/report_index_guard.py`
- `tests_v9/test_report_index_guard.py`
- `.github/workflows/report-index.yml`
- `scripts/ci/no_report_only_change_guard.py`
- `tests_v9/test_no_report_only_change_guard.py`
- `.github/workflows/no-report-only-change.yml`

## Verification

Direct guards passed:

```text
production_evidence_pack_check_ok
route_residual_classification_check_ok
report_index_check_ok
no_report_only_change_guard_ok
production_certification_checklist_ok
p1_main_decomposition_guard_ok
p2_main_decomposition_guard_ok
route_mount_inventory_check_ok
api_versioning_policy_check_ok
health_readiness_schema_guard_ok
contract_capabilities_schema_check_ok
test_dependency_inventory_check_ok
dependency_inventory_check_ok
dependency_conflict_inventory_check_ok
direct_dependency_bundle_check_ok
internal_graphql_security_guard_ok
health_alias_contract_guard_ok
edge model contract guard passed
edge production readiness guard passed
production honesty guard passed
```

New tests passed:

```text
7 passed in 12.50s
```

Targeted runtime smoke tests passed separately:

```text
26 passed, 1 skipped in 12.69s
```

The skipped test is the already-documented Redis live optional test requiring `WEATHER_REDIS_INTEGRATION_URL`; it maps directly to `P-CERT-3`.

## Note on runtime_real_smoke.sh in this environment

The smoke script's static guard phase completed successfully. The full script hit the conversation execution timeout while entering the targeted pytest phase, so the targeted pytest set was run directly and passed. This is a tooling timeout, not a test failure.

## Current status

```text
P0/P1/P2 decomposition complete.
Production evidence discipline added.
Runtime smoke profile added.
Route residual classification added.
Still not production certified until P-CERT evidence is attached from real CI/deployment.
```
