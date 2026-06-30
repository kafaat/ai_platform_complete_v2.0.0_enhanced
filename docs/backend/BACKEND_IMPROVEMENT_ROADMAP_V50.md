# Backend Improvement Roadmap v50

## Phase 1 — Governance guardrails
- Keep `SERVICE_REGISTRY.md` updated.
- Add a CI test that validates generated inventory and product defaults.
- Require connector contracts for timeout/retry/circuit breaker/fail-safe.

## Phase 2 — Field Intelligence Backbone
- Add a read-only field intelligence composer.
- Return evidence references, quality warnings, imagery/weather coverage, and operation context.
- Reuse existing `ai-context-pack`; do not duplicate domain logic.

## Phase 3 — Imagery Job Lifecycle
- Add persistent jobs for 24-month backfill.
- Expose progress, skipped scenes, failures, COG readiness, and retry.
- Feed completed jobs back into the two-year timeline.

## Phase 4 — Productivity Zones and VRA
- Generate productivity zones from multi-date imagery.
- Export prescriptions as neutral GeoJSON/CSV first.
- Later add machine/work-plan adapters.

## Phase 5 — Evidence-grounded AI actions
- AI can propose actions but cannot execute without explicit permission and RBAC.
- Every answer should show evidence chips and data freshness.
- Every action should create an audit event.
