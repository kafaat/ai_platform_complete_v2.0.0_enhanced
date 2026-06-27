# GIS Phase 11 — Federated Agents + Autonomous Operations

Implemented on top of Phase 10.

## Added

- `shared/federated_agents_phase11.py`
  - Agent context builder over CanonicalFieldState.
  - Specialist agents: planner, water, agronomy, disease, soil, economics, operations, safety.
  - Consensus kernel with conflict detection and safety vetoes.
  - Autonomous operation plan builder with safety gates and rollback plan.
  - Shadow/canary/champion-challenger experiment plan.
  - Consensus quality evaluator.
  - Full Phase 11 federation cycle.

- `services/sahool-platform/api/phase11_federated_agents.py`
  - `/v1/phase11/federation/context`
  - `/agents/propose`
  - `/consensus`
  - `/operation-plan`
  - `/experiments/shadow`
  - `/quality`
  - `/cycle`

- `migrations/v120_phase11_federated_agents.sql`
  - `agent_federation_cycles`
  - `agent_proposals`
  - `federated_policy_experiments`
  - RLS policies.

- Tests:
  - `shared/test_federated_agents_phase11.py`
  - `services/sahool-platform/tests/test_phase11_federated_agents_api.py`

## Runtime intent

Phase 11 converts the platform from single-engine decisioning into an auditable multi-agent operating layer:

```text
CanonicalFieldState
  → specialist agents
  → consensus + vetoes
  → operation plan
  → shadow/canary experiment
  → Phase 9 actuator/verification runtime
  → Phase 10 learning
```

The code remains deterministic for CI; production can replace individual specialist proposals with LangGraph/Temporal/MCP/LLM or ML-backed adapters while keeping the same contracts.
