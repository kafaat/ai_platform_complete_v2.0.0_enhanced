# SAHOOL Phase 7 — IoT Execution Adapter Runtime

## Scope
Continued after Phase 6 Feature Store + Model Registry by strengthening Phase 9 autonomous execution with a safe IoT adapter runtime.

## Implemented
- Added `shared/iot_execution_runtime.py`.
- Added fail-safe protocol capabilities for:
  - manual work orders
  - MQTT
  - Modbus TCP
  - LoRaWAN
  - pivot API
  - pump API
- Added explicit dispatch envelope generation.
- Added deterministic dispatch simulation/queue contract.
- Real physical effect requires both:
  - adapter mode `real`
  - `physical_actuation_enabled=true`
  - command is not `dry_run`
- Added telemetry summarization for closed-loop verification.
- Added Phase 9 endpoints:
  - `POST /v1/phase9/autonomy/iot/dispatch/preview`
  - `POST /v1/phase9/autonomy/iot/dispatch/simulate`
  - `POST /v1/phase9/autonomy/iot/telemetry/verify`
- Added persistence for audited IoT dispatch batches.
- Added migration `v109_phase9_iot_execution_adapters.sql` and registered it in `MANIFEST.txt`.
- Added regression tests.

## Safety posture
This patch is intentionally fail-closed. It does not perform direct physical device I/O. The runtime emits audited dispatch contracts that can be consumed by controlled workers/adapters. This preserves the Phase 9 safety chain: decision → guardrails → outbox → adapter contract → telemetry verification.
