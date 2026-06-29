# SAHOOL Phase 2 — AI Runtime E2E + Gateway + Web Binding Verification

Date: 2026-06-26
Artifact: `sahool_phase12_phase2_ai_runtime_e2e_web_bound_20260626.zip`

## Scope

This patch closes Phase 2 after the Phase 1 compose activation of:

- `sahool-rag-retrieval`
- `sahool-knowledge-graph`
- `sahool-ai-agronomist`
- worker readiness probes

The goal of Phase 2 is to prove these services are not just containers in compose, but are reachable through the gateway and bound to a real web flow.

## Changes implemented

### 1. Web → Gateway → AI Agronomist binding

Updated `frontend/src/sections/ChatbotPage.tsx` so the AI chat flow now calls:

```text
POST /api/ai-agronomist/chat
```

instead of the legacy supervisor-agent path:

```text
POST /api/agent/query
```

The request now includes:

- `question`
- `field_id` from the shared `useFieldContextStore`
- `language`
- `current_field_state` client context block
- recent conversation turns

The UI labels were updated from Claude-specific wording to `SAHOOL AI Runtime · RAG/KG/FieldState`.

### 2. AI Agronomist runtime endpoints

Extended `services/ai_agronomist/main.py` with production-facing compatibility endpoints:

```text
POST /query
POST /chat
POST /explain
POST /recommend
```

All endpoints are evidence-only and return:

- `annotations.rag`
- `annotations.knowledge_graph`
- `annotations.canonical_field_state`
- `evidence_ids`
- `confidence`
- `guardrail_result`
- `decision_authority = field_intelligence_coordinator`

`/recommend` intentionally does not emit prescriptions, tasks, doses, or execution actions. It remains evidence-only for UI compatibility.

### 3. CanonicalFieldState integration

`ai_agronomist` now attempts to fetch field state from:

```text
GET /internal/fields/{field_id}/state?tenant_id=...
```

using:

```text
X-Agent-Token: SAHOOL_AGENT_TOKEN
```

This keeps the legal field state inside `sahool-platform` as the source of truth. If the internal field-state dependency is unavailable, the runtime degrades honestly by marking field state as unavailable rather than fabricating values.

### 4. Safety contract preserved

RAG/KG remain annotation-only. The runtime verifies that RAG/KG payloads do not emit structured decision keys such as:

- `recommendation`
- `prescription`
- `task`
- `dose`
- `irrigation_schedule`

Final decisions remain owned by:

```text
field_intelligence_coordinator → guardrails → Phase 9 autonomy
```

### 5. Gateway / compose contract tests

Added:

```text
tests_v9/runtime_activation/test_phase2_ai_gateway_web_binding_static.py
```

It verifies:

- Chatbot uses `/api/ai-agronomist/chat`
- Chatbot does not call `/api/chat` or legacy `/api/agent/query`
- AI Agronomist exposes `/query`, `/chat`, `/explain`, `/recommend`
- AI Agronomist fetches CanonicalFieldState through the internal service-to-service endpoint
- Nginx routes `/api/rag/`, `/api/knowledge-graph/`, `/api/ai-agronomist/` with auth and tenant header propagation
- Compose has strict dependencies and healthchecks
- Vite dev proxy preserves gateway paths

### 6. Frontend TypeScript test globals fix

Updated `frontend/tsconfig.json` to include:

```json
"types": ["vitest/globals"]
```

This fixes the pre-existing `tsc --noEmit` failure caused by test files using Vitest globals.

## Verification performed

### Python compile

```text
1327 Python files compiled successfully
0 failed
```

### Runtime activation regression tests

```text
8 passed
```

### RAG/KG/MCP and production completion targeted tests

```text
21 passed
```

### Frontend targeted Vitest

```text
src/sections/ChatbotPage.endpoint.test.ts
2 passed
```

### Frontend typecheck

```text
npm run typecheck
passed
```

### Frontend production build

```text
npm run build
passed
```

## Not executed

Docker was not available in this environment, so these must still be run on the target machine:

```bash
docker compose -f docker-compose.v9.yml config
docker compose -f docker-compose.v9.yml up -d
docker compose -f docker-compose.v9.yml ps
curl http://localhost/api/rag/healthz
curl http://localhost/api/knowledge-graph/healthz
curl http://localhost/api/ai-agronomist/healthz
curl -X POST http://localhost/api/ai-agronomist/chat \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <JWT>' \
  -d '{"question":"ما حالة الحقل؟","field_id":"<field_id>","language":"ar"}'
```

## Result

Phase 2 is now implemented at code/static/runtime-contract level:

```text
Web Chatbot
↓
Nginx / Gateway
↓
AI Agronomist Runtime
↓
RAG Retrieval + Knowledge Graph + CanonicalFieldState
↓
Evidence-only answer
↓
Decision authority remains Field Intelligence Coordinator
```
