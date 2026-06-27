# SAHOOL Phase 10 — Reliability, Load, Chaos, and Recovery Harness

Date: 2026-06-26

## Scope

This patch adds a runtime validation harness for the production stack after AI runtime, Feature Store, IoT adapters, Marketplace sandbox, and Federated Agent consensus were integrated.

The focus is not adding product features; it is proving the platform can survive load, dependency failures, and recovery without silent corruption of field imagery, raster tiles, AI responses, outbox events, or worker readiness.

## Added files

- `scripts/load/k6_field_imagery_ai.js`
- `scripts/load/run_load_tests.sh`
- `scripts/chaos/run_chaos_tests.sh`
- `scripts/recovery/recovery_smoke.sh`
- `tests/reliability/test_phase10_reliability_harness_contracts.py`

## Load test coverage

The k6 scenario covers:

- Raster available dates
- Raster TileJSON with explicit `index`, `date`, and version parameter
- AI agronomist chat with field context requirement
- Runtime thresholds for HTTP failures and P95 latency
- Fail-closed assertion to prevent silent successful AI advice with no context/evidence

## Chaos coverage

The chaos runner validates stop/restart behavior for:

- `sahool-redis`
- `sahool-nats`
- `sahool-raster-service`
- `sahool-rag-retrieval`
- `sahool-knowledge-graph`
- `sahool-ai-agronomist`

After each restart it runs runtime smoke checks and can optionally trigger outbox and field/imagery/AI E2E checks if credentials are supplied.

## Recovery coverage

The recovery smoke script checks:

- Gateway health for raster, RAG, Knowledge Graph, and AI Agronomist
- Raster available dates
- Versioned TileJSON
- Outbox reliability when a JWT is provided

## Expected local commands

```bash
docker compose -f docker-compose.v9.yml up -d
BASE_URL=http://localhost ./scripts/runtime_smoke.sh
BASE_URL=http://localhost FIELD_ID=<field> TENANT_ID=<tenant> SAHOOL_JWT=<jwt> ./scripts/load/run_load_tests.sh
BASE_URL=http://localhost FIELD_ID=<field> TENANT_ID=<tenant> SAHOOL_JWT=<jwt> ./scripts/chaos/run_chaos_tests.sh
BASE_URL=http://localhost FIELD_ID=<field> TENANT_ID=<tenant> SAHOOL_JWT=<jwt> ./scripts/recovery/recovery_smoke.sh
```

## Acceptance criteria

- No unexplained 5xx spikes under moderate load.
- Raster TileJSON/PNG remains date/index/version scoped.
- AI Agronomist does not silently answer field-specific advice without field context.
- RAG/KG failures are visible as degraded/fail-closed behavior.
- NATS/Redis failures recover without lost outbox state.
- Workers do not enter restart loops.
- Gateway routes remain stable after dependency restarts.

## Limitations

Docker and k6 are not available in the current execution environment, so this patch provides executable harnesses and static regression tests. Full runtime validation must be run on the local Docker host.
