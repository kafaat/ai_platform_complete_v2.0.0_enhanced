# Actuator Device Safety Certification Continuation — 2026-07-12

## Scope
Continuation of the governed chain:

`water ledger → decision → execution request → actuator consumer → receipt → timeline`

This increment focuses on the last pre-dispatch physical-safety boundary.

## Findings fixed

### 1. Authoritative target / payload device mismatch
The execution request contains an authoritative `target_id`, while `command_payload` also carries `device_id`. Previously the consumer trusted the payload device and did not require equality. A malformed or compromised payload could therefore redirect an authorized request to another device.

Fix: `_plan_dispatch_execution` now returns a terminal `target_mismatch` result unless `target_id == device_id`.

### 2. Missing runtime device readiness gate
The consumer previously checked the tenant-wide emergency stop but did not verify the canonical device registry before publishing.

Fix: added `_validate_dispatch_device` and pure `_device_dispatch_gate` enforcing, fail-closed:

- device exists in `iot_devices`;
- device belongs to the requested tenant under tenant RLS;
- device type is `actuator`;
- device field matches command `field_id` when supplied;
- device status is `online`;
- `last_seen_at` is present and no older than `ACTUATOR_DEVICE_STALE_SECONDS`;
- future/invalid telemetry timestamps are rejected.

### 3. Scoped emergency-stop recheck
The consumer now rechecks the kill switch after parsing and validating the command with:

- tenant;
- field;
- device/valve.

This prevents a field- or valve-specific stop from being bypassed by the earlier tenant-only check.

## Configuration

```env
ACTUATOR_DEVICE_STALE_SECONDS=900
```

Added to `.env.example` and `docker-compose.v9.yml`. The fixed compose file has no actuator-service node to patch.

## Verification

- Actuator focused safety suite: `40 passed`.
- Expanded water/decision/timeline/actuator suite: `59 passed, 4 skipped`.
- Skips require a real PostgreSQL integration database.
- `py_compile` passed for `actuator_runtime.py`.
- `docker-compose.v9.yml` and `docker-compose.fixed.yml` parsed successfully as YAML.

## Remaining runtime-only gates

1. Real PostgreSQL RLS and atomic-claim tests.
2. Dual-consumer race and restart tests in Compose.
3. MQTT simulation with receipt failure and recovery.
4. Device-side enforcement of the stable `idempotency_key`; MQTT QoS 1 is at-least-once and may duplicate delivery.
5. Real-device activation remains prohibited until staging certification succeeds.
