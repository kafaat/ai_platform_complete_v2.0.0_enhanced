# SAHOOL Phase 1 AI Runtime Compose Implementation — 2026-06-26

## Scope
Implemented the first runtime activation block requested for:

- `rag-retrieval`
- `knowledge-graph`
- `ai_agronomist`
- worker readiness

This patch makes the canonical `docker-compose.v9.yml` self-contained for the core AI evidence runtime instead of relying on the separate RAG/KG overlay.

## Changes

### 1. Canonical compose integration
Added the following services directly to `docker-compose.v9.yml`:

- `sahool-rag-retrieval`
- `sahool-knowledge-graph`
- `sahool-ai-agronomist`

Each service includes:

- `restart: unless-stopped`
- `security_opt: no-new-privileges:true`
- `logging: *default_logging`
- `sahool-internal` network
- Docker healthcheck
- explicit dependency ordering

`ai_agronomist` now starts only after RAG, KG, and Guardrails are healthy.

### 2. RAG readiness
Added `/readyz` to `services/rag-retrieval/main.py`.

Readiness checks Qdrant reachability instead of only returning process-alive status.

### 3. Knowledge Graph readiness
Added `/readyz` to `services/knowledge-graph/main.py`.

Readiness validates that the graph store is accessible and returns edge count.

### 4. AI Agronomist runtime
Added runtime service files:

- `services/ai_agronomist/main.py`
- `services/ai_agronomist/Dockerfile`
- `services/ai_agronomist/requirements.txt`

The AI Agronomist is intentionally **evidence-only**:

- it gathers RAG annotations;
- it queries KG relationships;
- it does not emit final recommendations/tasks/prescriptions;
- final decision authority remains with `field_intelligence_coordinator` + Guardrails + Phase 9 execution.

### 5. Gateway routes
Added Nginx upstreams and routes:

- `/api/rag/` → `sahool-rag-retrieval`
- `/api/knowledge-graph/` → `sahool-knowledge-graph`
- `/api/ai-agronomist/` → `sahool-ai-agronomist`

Routes are protected through the existing auth verification model and tenant header reinjection.

### 6. Worker readiness
Added readiness healthchecks for:

- `sahool-weather-polygon-worker`
- `sahool-weather-signal-engine`

Added file-based worker readiness/heartbeat probes:

- `services/weather-polygon-worker/worker_health_probe.py`
- `services/weather-signal-engine/worker_health_probe.py`

Weather signal engine writes readiness after DB pool initialization and refreshes heartbeat after successful cycles.

Weather polygon worker now stays healthy but explicitly idle when `WEATHER_GRID_PIPELINE_ENABLED=0`, instead of exiting and triggering restart loops. When enabled, it writes readiness after DB/NATS initialization.

### 7. Regression tests
Added:

- `tests_v9/runtime_activation/test_phase1_ai_runtime_compose_static.py`

The test verifies:

- the three AI runtime services exist in canonical compose;
- healthchecks exist;
- AI Agronomist depends on RAG/KG health;
- Nginx routes exist;
- worker readiness healthchecks exist.

## Verification

Executed locally in this environment:

```bash
python -m py_compile ...
```

Result:

```text
compiled 1326 failed 0
```

Executed targeted regression test:

```bash
pytest -q tests_v9/runtime_activation/test_phase1_ai_runtime_compose_static.py
```

Result:

```text
3 passed
```

`docker compose config` could not be executed in this environment because Docker is unavailable here, but YAML parsing with PyYAML succeeded and static compose checks passed.

## Remaining runtime acceptance on the deployment machine

Run on the host with Docker:

```bash
docker compose -f docker-compose.v9.yml config
docker compose -f docker-compose.v9.yml up -d sahool-rag-retrieval sahool-knowledge-graph sahool-ai-agronomist sahool-weather-signal-engine
```

Then verify:

```bash
curl http://localhost/api/rag/healthz
curl http://localhost/api/knowledge-graph/healthz
curl http://localhost/api/ai-agronomist/healthz
```

For authenticated routes, use a valid JWT because the gateway applies `auth_request`.
