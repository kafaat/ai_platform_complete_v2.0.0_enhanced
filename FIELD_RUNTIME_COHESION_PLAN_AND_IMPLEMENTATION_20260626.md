# Field Runtime Cohesion — Plan and Implementation

## Goal
Unify the existing field brain so `CanonicalFieldState` becomes the only source of truth for downstream twins, Phase 6 precision-agriculture features, and recommendation execution lifecycle.

## Implemented
- Added `shared/field_runtime_cohesion.py`.
- Added canonical state envelope with stable `state_id`.
- Added derived unified digital-twin view.
- Added recommendation lifecycle state machine:
  - proposed
  - guardrails_blocked
  - approved
  - dispatched
  - executed
  - verified
  - learned
  - cancelled
- Added closed-loop outcome feedback candidate event.
- Added Phase 6 runtime input adapter derived from the unified twin view.
- Added API adapter: `services/sahool-platform/api/field_runtime_cohesion.py`.
- Added migration `v101_field_runtime_cohesion.sql`.
- Added tests in `shared/test_field_runtime_cohesion.py`.

## Runtime rule
No downstream module should recompute field state from raw signals when a canonical state snapshot exists. All views must reference `source_state_id`.

## Remaining live integration
- Persist these payloads through the actual DB adapter in platform runtime.
- Publish recommendation lifecycle events to NATS/outbox.
- Connect verified outcomes to the future Feature Store.
