# M2.9 Controller & Edge Adapter Framework

## Scope
Implemented a vendor-neutral, fail-closed controller/edge boundary for irrigation assets. The framework normalizes telemetry, validates controller identity and capability handshake, rejects replay/out-of-order messages, computes a governed controller capability snapshot, and prepares only non-dispatchable command request envelopes.

## Added
- `services/sahool-platform/api/controller_edge_adapter.py`
- `migrations/v175_controller_edge_adapter_framework.sql`
- `tests_v9/test_controller_edge_adapter.py`
- `scripts/ci/irrigation_controller_edge_m2_9_guard.py`

## Safety properties
- Read-only is the default operating mode.
- Dry-run mode cannot dispatch.
- Sequence number and observation timestamp replay protection.
- Freshness, connection, certification, capability, alarm, and identity gates.
- Controller capability digest binds handshake and latest telemetry.
- Human-approved and guarded modes require an execution authorization identifier.
- Command requests always persist `dispatch_allowed = false`; this phase does not call actuator-service or any vendor API.
- Tenant-bound foreign keys, RLS and FORCE RLS on all new tables.
- No credentials, tokens, passwords, or vendor secrets are persisted.

## Database objects
- `irrigation_controller_handshakes`
- `irrigation_controller_telemetry`
- `canonical_controller_capabilities`
- `irrigation_controller_command_requests`

## Protocol contract
Supported protocol identifiers: MQTT, Modbus TCP, Modbus RTU, HTTP, OPC-UA, vendor API and local PLC. This is a normalized contract only; no protocol-specific network driver was activated.

## Verification
- M2.9 focused tests: 7 passed.
- Combined controller/capability/water/MPC regression: 81 passed, 0 failed, with DeprecationWarning promoted to error.
- M2.1 through M2.9 static guards: PASS.
- Python compilation: PASS.

## Certification limits
Not certified in this environment:
- PostgreSQL migration and live cross-tenant RLS test.
- Real MQTT/Modbus/OPC-UA controller handshake.
- Device clock drift and duplicate-message behavior under a live broker.
- actuator-service delivery, field execution, acknowledgement, or receipt reconciliation.
- Hardware emergency-stop and local PLC interlock validation.

## Next stage
M2.10 Commissioning & Certification: field evidence packs, installation checks, calibrated flow/pressure verification, controller handshake certification, signed acceptance, expiry/re-certification, and a hard gate before a capability graph becomes executable.
