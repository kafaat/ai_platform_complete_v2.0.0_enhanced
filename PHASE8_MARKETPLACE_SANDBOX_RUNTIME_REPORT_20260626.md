# Phase 8 — Marketplace Sandbox + Plugin Runtime Guardrails

## Implemented

- Added `shared/marketplace_plugin_runtime.py` as a deterministic runtime safety layer for Phase 12 plugins.
- Added fail-closed plugin execution planning:
  - approved app required
  - active installation required
  - declared permission required
  - quota projection required
  - sensitive actions require review and cannot execute directly
- Added least-privilege sandbox context:
  - read-only filesystem
  - no raw DB/NATS credentials
  - tenant-scoped references only
  - direct DB/NATS/host filesystem/physical actuation denied
- Added plugin event envelopes with schema versioning and secret scrubbing.
- Added plugin output validation to block direct side effects:
  - direct DB writes
  - raw NATS publish
  - host file writes
  - secret reads
  - direct actuator commands
  - model promotion outside Phase 10 registry
- Added Phase 12 API endpoints:
  - `POST /v1/ecosystem/plugins/runtime/plan`
  - `POST /v1/ecosystem/plugins/runtime/validate-output`
  - `POST /v1/ecosystem/plugins/runtime/event-envelope`
  - `POST /v1/ecosystem/plugins/runtime/report`
- Added migration `v110_phase12_plugin_sandbox_runtime.sql` and registered it in `migrations/MANIFEST.txt`.
- Added regression tests for shared runtime contracts and API endpoints.

## Safety posture

Plugins remain proposal-only by default. They can propose recommendations, alerts and events, but they cannot directly mutate canonical field state, publish raw NATS events, promote models, or dispatch actuators. Sensitive operations are routed to Phase 9 or Phase 10 governed workflows.
