# SAHOOL Phase 3 — Runtime E2E + Integration Hardening

## Scope
This patch turns the previously integrated AI/RAG/KG services into a runtime-verifiable flow with gateway, field imagery, AI evidence, and event/audit checks.

## Added
- `scripts/check_gateway_routes.sh` — static gateway/compose route contract gate.
- `scripts/runtime_smoke.sh` — live health/readiness probe through nginx/gateway.
- `scripts/e2e/e2e_field_imagery_ai.sh` — authenticated live flow for field state, imagery dates, TileJSON, and AI Advisor evidence.
- `tests/e2e_runtime/test_phase3_runtime_integration_contracts.py` — regression contracts for routes, AI evidence-only behavior, internal event endpoint, and script safety.

## Code hardening
- `ai_agronomist` now records a best-effort internal AI advice audit event after evidence assembly.
- `sahool-platform` now exposes protected service-to-service `/internal/events/ai-advice` to record `AI_SUGGESTION` through the platform outbox.
- AI Advisor remains evidence-only and explicitly delegates final decision authority to `field_intelligence_coordinator`.

## Runtime acceptance
Run on a host with Docker:

```bash
docker compose -f docker-compose.v9.yml config
docker compose -f docker-compose.v9.yml up -d
docker compose -f docker-compose.v9.yml ps
./scripts/check_gateway_routes.sh
BASE_URL=http://localhost ./scripts/runtime_smoke.sh
SAHOOL_JWT=<jwt> TENANT_ID=<tenant> FIELD_ID=<field> BASE_URL=http://localhost ./scripts/e2e/e2e_field_imagery_ai.sh
```

## Notes
Docker is not available in the current execution environment, so live container startup remains a host-side acceptance step. Static/compile/regression tests are included to prevent route drift and evidence-runtime regression.

## Verification performed in this environment

- Python compile: `1328 compiled, 0 failed`.
- YAML parse: `docker-compose.v9.yml` parsed successfully with `44` services.
- Gateway static route check: passed for `/api/raster/`, `/api/v1/`, `/api/rag/`, `/api/knowledge-graph/`, `/api/ai-agronomist/`, `/api/guardrails/`, `/api/soil/`.
- Regression tests: `18 passed` across production RAG/KG/MCP, final production completion, and Phase 3 runtime integration contracts.
- Frontend package tests/build were not run here because `frontend/node_modules` is not present in the extracted ZIP and internet access is unavailable for installing dependencies.
- Docker live runtime was not run here because Docker is not available in the execution environment.
