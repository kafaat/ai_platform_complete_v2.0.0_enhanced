# Phase 9 — Federated Agent Consensus Runtime Hardening

Date: 2026-06-26

## Scope

This patch continues the post-Phase-12 hardening track by strengthening Phase 11 federated agents with production-oriented consensus controls. The goal is to ensure agents remain proposal-only, conflicts are explicit, and no high-impact field operation can bypass Phase 9 guardrails.

## Implemented changes

### 1. Federated-agent runtime guard layer

Added:

- `shared/federated_agent_runtime.py`

Capabilities:

- reputation-weighted consensus;
- bounded agent reputation normalization;
- explicit conflict-pair detection;
- safety veto handling;
- fail-closed resolution status;
- least-privilege authority envelopes;
- federation event envelopes for outbox/NATS publishing;
- deterministic reputation updates from observed outcomes.

### 2. New Phase 11 runtime API endpoints

Extended:

- `services/sahool-platform/api/phase11_federated_agents.py`

Added endpoints:

- `POST /v1/phase11/federation/runtime/resolve`
- `POST /v1/phase11/federation/runtime/authority-envelope`
- `POST /v1/phase11/federation/runtime/reputation/update`
- `POST /v1/phase11/federation/runtime/event-envelope`

The existing `/cycle` endpoint now also returns:

- `runtime_resolution`
- `authority_envelope`
- `event_envelope`

### 3. Fail-closed authority model

Phase 11 agents cannot execute field actions directly.

High-impact actions such as:

- `irrigate`
- `fertilize`
- `spray`
- `actuate`

always require the next gate:

- `phase9_guardrails`

The authority envelope sets:

- `may_execute = false`

for all Phase 11 outputs.

### 4. Persistence migration

Added:

- `migrations/v111_phase11_federated_agent_runtime.sql`

Registered in:

- `migrations/MANIFEST.txt`

New tables:

- `agent_reputation_scores`
- `agent_conflict_resolutions`
- `agent_authority_envelopes`

All tenant-scoped tables include RLS policies using `current_setting('app.tenant_id', true)`.

### 5. Persistence adapter hardening

Updated:

- `services/sahool-platform/api/phase_runtime_store.py`

Now persists runtime resolution and authority envelope when present.

### 6. Regression tests

Added:

- `shared/test_federated_agent_runtime.py`
- `services/sahool-platform/tests/test_phase11_runtime_api.py`

Coverage includes:

- safety veto blocking;
- high-impact action requiring human approval;
- authority envelope never allowing direct execution;
- reputation penalty on safety incidents;
- event envelope generation;
- API runtime resolution;
- `/cycle` response includes runtime guard outputs.

## Verification

Executed checks:

```text
Python compile: 1342 compiled, 0 failed
YAML parse: docker-compose.v9.yml parsed successfully, 44 services
Targeted tests: 27 passed
Security audit: hard failures 0
```

Security audit warnings remain limited to known BYPASSRLS comments/jobs/bootstrap/guard contexts and did not produce hard failures.

## Production boundary

This patch does not connect federated agents to physical equipment. The safe chain remains:

```text
Phase 11 agents propose
↓
Federation runtime resolves consensus
↓
Authority envelope restricts execution
↓
Phase 9 guardrails / HITL
↓
IoT execution adapter dry-run or approved runtime
```

