# Production Evidence Pack

This evidence pack prevents report-only certification. The repository remains `release_candidate_not_production_certified` until real CI/deployment artifacts verify every non-waivable blocker.

## Evidence files

### P-CERT-2 — Connected transitive lock generation

- File: `certification/evidence/transitive_locks_summary.json`
- Required status: `verified`
- Waivable: `false`
- Minimum fields when verified: `status, command, index_url_policy, lock_files, timestamp_utc`

### P-CERT-1 — Full branch CI

- File: `certification/evidence/ci_summary.json`
- Required status: `verified`
- Waivable: `false`
- Minimum fields when verified: `status, branch, commit, jobs, timestamp_utc`

### P-CERT-4 — ONNX/SAM2 model provisioning

- File: `certification/evidence/model_provisioning_summary.json`
- Required status: `verified`
- Waivable: `false`
- Minimum fields when verified: `status, edge_readiness_mode, edge_production_required, artifacts, timestamp_utc`

### P-CERT-3 — Redis live integration

- File: `certification/evidence/redis_live_test_summary.json`
- Required status: `verified`
- Waivable: `true`
- Minimum fields when verified: `status, redis_url_kind, test_command, readyz_cache_backend, timestamp_utc`

### GUARDS — Guard results summary

- File: `certification/evidence/guard_results_summary.json`
- Required status: `verified`
- Waivable: `false`
- Minimum fields when verified: `status, guards, timestamp_utc`

## State machine

Allowed evidence states: `pending`, `evidence_attached`, `verified`, `waived_with_reason`, `failed`.

Non-waivable: `P-CERT-1`, `P-CERT-2`, `P-CERT-4`, and `GUARDS`.

`P-CERT-3` may be waived only with an explicit reason and only when Redis is not used for correctness/state in the target deployment.
