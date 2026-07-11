# WX-11.2 — Evaluation Run + Candidate Artifact Boundary

Implemented an authoritative, append-only registration boundary for reproducible model-evaluation evidence and candidate artifact metadata.

## Added
- migration `009_model_evaluation_run.sql`
- `POST /v1/learning/evaluation-runs`
- BFF `POST /api/v1/learning/evaluation-runs`
- deterministic idempotency and artifact SHA-256 uniqueness
- dataset-count parity against authoritative attributed outcomes
- transactional `MODEL_EVALUATION_RUN_CREATED` outbox event
- structural boundary gate and focused contract tests

## Explicit exclusions
No training, optimizer update, model-registry promotion, active-model mutation, redispatch, MQTT, or actuator call.

## Verification
- Python compile: PASS
- WX-11.2 boundary gate: PASS
- focused tests: PASS
- real PostgreSQL migration/concurrency checks remain CI-owned
