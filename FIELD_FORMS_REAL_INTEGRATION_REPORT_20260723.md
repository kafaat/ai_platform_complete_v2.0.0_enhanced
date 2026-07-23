# GAP-FIELD-FORMS-01 — Real Integration Report

Date: 2026-07-23
Base: `sahool_main_3f2a010_IRR_F01_executed_20260723`
Source reviewed: `OKComputer_FastAPI_认证评估.zip`

## Applied selectively

- Added persistent `DeviceIdService` using secure storage and cryptographic randomness.
- Preserved the device identity across logout by replacing broad secure-storage deletion with session-key deletion only.
- Added `FieldFormsCoordinator` to open Hive stores, refresh the authenticated BFF client, download field packages, and drain submissions FIFO.
- Wired coordinator startup after authentication and cleanup on AuthGate disposal.
- Wired package synchronization when a concrete Field Workspace is opened.
- Added `X-Device-Id` to submission requests; the existing download path already sends actor/device query parameters.
- Exposed the existing configured Dio instance through a read-only getter, retaining JWT, request IDs, refresh, and retry behavior.
- Added weekly Dependabot updates for SHA-pinned GitHub Actions.
- Added adapted Flutter tests and Python static regression guards.

## Intentionally not applied

- No wholesale branch replacement.
- No older Compose replacement.
- No blind application of `field_forms_slice3.patch`.
- No duplicate backend/BFF implementation.

## Verification

- Focused Python/static Field Forms suite: PASS.
- Python compile sweep for affected backend services: PASS.
- Flutter/Dart runtime tests: not executed because Flutter/Dart are unavailable in this environment; test files were updated to the actual API contract.

## Remaining live proof

Production certification still requires a Flutter runner plus live BFF/scout-ingest/PostgreSQL execution, including offline reconnect and device-rotation scenarios.
