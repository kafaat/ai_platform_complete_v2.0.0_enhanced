# Raw Weather Data Processing — Weather Container Verification and Fix

Date: 2026-07-09
Artifact base: `sahool_ai_platform_57cf56e_fleet_green_reconciled_current.zip`

## Executive verdict

`weather-service` did **not** previously have a dedicated raw-weather processing boundary. It exposed current/forecast/historical/tiles and operation-window endpoints, but no explicit endpoint for raw weather QA/provenance before derived agricultural rules.

This pass added a non-breaking raw-data endpoint:

```text
POST /v1/weather/raw/process
```

The endpoint is intentionally QA/provenance only:

```text
fabricated_weather = false
operation_window_computed = false
indicator_computed = false
raw_data_processing = true
```

## Files added

```text
services/weather-service/raw_weather_processing.py
services/weather-service/tests/test_raw_weather_processing.py
scripts/ci/raw_weather_processing_contract_guard.py
tests_v9/test_raw_weather_processing_contract_guard.py
.github/workflows/raw-weather-processing-contract.yml
RAW_WEATHER_PROCESSING_IMPLEMENTATION_REPORT_20260709.md
```

## Files modified

```text
services/weather-service/main.py
services/weather-service/weather_runtime.py
scripts/ci/runtime_real_smoke.sh
SERVICE_REGISTRY.md
route_inventory.generated.json
route_inventory.csv
route_mount_inventory.generated.json
route_mount_inventory.csv
api_versioning_inventory.generated.json
api_versioning_inventory.csv
REPORT_INDEX.md
```

## Endpoint contract

Request model:

```text
lat
lon
source_kind: current | forecast | historical | tile_sample
model
days
start_date / end_date for historical
include_payload
max_items
```

Response includes:

```text
source metadata
location
model
raw_observation_count
numeric_field_count
numeric_summary
provenance
data_quality
flags
optional raw_payload
```

## Container verification

`services/weather-service/Dockerfile` already copies the full service directory:

```dockerfile
COPY services/weather-service/ /app/
```

Therefore the new runtime file is included in the container without adding a bespoke COPY line.

Docker liveness remains correctly bound to:

```text
/healthz
```

not `/readyz`.

## Verification

Targeted tests:

```text
services/weather-service/tests/test_raw_weather_processing.py ...
tests_v9/test_raw_weather_processing_contract_guard.py .
4 passed
```

Existing weather runtime tests:

```text
15 passed
```

Guards passed:

```text
raw_weather_processing_contract_ok
raw_data_processing_contract_ok
runtime_container_deep_contract_guard_ok
container_fleet_contract_guard_ok
ai_container_contract_guard_ok
pip_audit_resolution_guard_ok
route_mount_inventory_check_ok
api_versioning_policy_check_ok
health_readiness_schema_guard_ok
contract_capabilities_schema_check_ok
report_index_check_ok
```

Inventory now reports:

```text
28 services
874 routes
```

## Production note

This is not a replacement for Redis live integration or full Docker build matrix. It only closes the missing raw-weather QA/provenance boundary and confirms the weather container includes the new module via full service-dir copy.
