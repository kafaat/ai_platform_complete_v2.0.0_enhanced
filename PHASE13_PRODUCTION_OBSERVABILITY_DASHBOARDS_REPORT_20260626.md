# Phase 13 — Production Observability Dashboards + Alert Rules

## Scope

This phase closes the gap between exported metrics and actual production monitoring. It adds Grafana dashboard provisioning, Prometheus SLO-style alerts, and a static observability validation gate that can run without Docker.

## Added assets

- `grafana/dashboards/dashboards.yml`
- `grafana/dashboards/json/sahool-production-overview.json`
- `grafana/dashboards/json/sahool-field-imagery-ai-runtime.json`
- `scripts/observability/validate_observability_assets.py`
- `tests/observability/test_phase13_observability_assets.py`

## Prometheus alert coverage

Added production-focused alerts for:

- Raster / TileJSON stack unavailable.
- AI advice stack degraded.
- Outbox backlog growth.
- Outbox publish failures.
- Marketplace plugin sandbox violations.
- IoT physical actuation blocked by guardrails.
- Mobile offline sync conflict spikes.
- Model promotion failures.

The alerts are defensive: if a metric is not exported yet, the expression yields no series rather than crashing Prometheus. Once the corresponding services export these counters, the rules become active automatically.

## Grafana dashboard coverage

### SAHOOL Production Overview

Covers:

- targets up/down
- HTTP 5xx rate
- p95 latency
- process memory
- NATS/event bus health

### SAHOOL Field Imagery AI Runtime

Covers:

- raster stack availability
- AI/RAG/KG/guardrails availability
- TileJSON/tile request rates
- AI advice request rates
- outbox backlog/failures
- cache/dependency degradation

## Validation

Run locally:

```bash
python scripts/observability/validate_observability_assets.py
pytest -q tests/observability/test_phase13_observability_assets.py
```

Full preflight:

```bash
./scripts/production_validation_gate.sh
python scripts/observability/validate_observability_assets.py
```

## Runtime verification

After Docker is running:

```bash
docker compose -f docker-compose.v9.yml up -d sahool-prometheus sahool-alertmanager sahool-grafana
curl -fsS http://localhost:9090/-/ready
curl -fsS http://localhost:3001/api/health
```

Then open Grafana and verify the `SAHOOL Production` folder contains the two dashboards.
