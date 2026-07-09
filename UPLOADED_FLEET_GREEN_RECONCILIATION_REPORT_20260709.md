# Uploaded `sahool_ai_platform_57cf56e_fleet_green.zip` Reconciliation Report — 2026-07-09

## Verdict

The uploaded `fleet_green` archive is **not the current corrected line**. It is missing the fixes that were added after the container-fleet work, including:

- raw raster data processing endpoint and guard
- Redis pip-audit resolution guard and unified Redis pin policy
- indicators container contract guard
- vegetation container contract guard
- AI container contract guard
- runtime container deep contract guard
- container fleet contract guard
- updated report index entries

Therefore, treating the uploaded archive as the final release candidate would regress the governance and runtime-container fixes.

## Critical gaps found in uploaded archive

| Area | Uploaded archive status | Current corrected status |
|---|---|---|
| Raw data processing | missing | `POST /raw/process` implemented in raster-service |
| Raw data guard | missing | `raw_data_processing_contract_guard.py` present |
| Redis pip-audit resolution | unresolved mixed pins | `redis==5.3.1` policy guarded |
| Indicators container guard | missing | present |
| Vegetation container guard | missing | present |
| AI container guard | missing | present |
| Container fleet guard | missing | present |
| Runtime deep container guard | missing | present |
| Report index | stale | updated |

## Redis finding in uploaded archive

The uploaded archive still contains mixed Redis specifiers:

```text
redis>=5.0.0
redis==5.3.1
```

This is exactly the type of resolver drift that previously caused the `pip-audit` job to fail with `ResolutionImpossible`.

## Reconciliation action

The corrected output package is based on the latest cumulative fixed working tree, not on the stale uploaded tree. This preserves the already-applied fixes:

- P0/P1/P2 decomposition
- production evidence/running smoke governance
- indicators container fix
- vegetation container fix
- AI container fix
- container fleet fix
- runtime container deep fix
- Redis pip-audit resolution fix
- raw data processing implementation

## Verification executed

Direct guards:

```text
raw_data_processing_contract_ok
pip_audit_resolution_guard_ok
indicators_container_contract_guard_ok
vegetation_container_contract_guard_ok
container_fleet_contract_guard_ok
ai_container_contract_guard_ok
runtime_container_deep_contract_guard_ok
report_index_check_ok
```

Targeted guard tests:

```text
test_raw_data_processing_contract_guard.py: passed
test_pip_audit_resolution_guard.py: passed
test_container_fleet_contract_guard.py: passed
test_ai_container_contract_guard.py: passed
test_runtime_container_deep_contract_guard.py: passed
test_vegetation_container_contract_guard.py: passed
test_indicators_container_contract_guard.py: passed
```

## Remaining production blockers

Unchanged:

- Docker build matrix in CI
- full branch CI
- connected transitive lock generation
- Redis live integration
- ONNX/SAM2 model provisioning
