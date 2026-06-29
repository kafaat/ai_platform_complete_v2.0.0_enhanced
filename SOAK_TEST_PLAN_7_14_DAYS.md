# SAHOOL 7-14 Day Soak Test Plan

## Goal

Prove production behavior under sustained live runtime load before any `Production Certified` claim.

## Target minimum scenario

- 1,000+ tenants
- 100,000+ fields
- Continuous field create/update/read traffic
- Continuous raster available-dates, TileJSON, and PNG tile churn
- AI advisor traffic with RAG/KG/Guardrails
- Mobile offline sync replay
- Outbox publish/retry/dead-letter checks
- Worker queues for plugins, model registry, actuator dispatch
- Chaos injections every 2 hours
- Replay verification every 1 hour

## Hard failure conditions

- Any AI fake fallback counted above zero
- Tile cache mismatch above zero
- Replay drift above zero
- Dead letters above zero without explicit accepted incident
- Outbox backlog age above 300 seconds
- Worker recovery rate below 99%
- HTTP 5xx rate above 0.5% for sustained windows

## Commands

```bash
TENANTS=1000 FIELDS=100000 DAYS=7 bash scripts/soak/run_soak_test.sh
# run live workload, chaos and recovery jobs, then aggregate metrics
python3 scripts/soak/soak_assertions.py --metrics-json soak-results/metrics.json
python3 scripts/soak/soak_report.py --scenario-json soak-results/scenario.json --metrics-json soak-results/metrics.json
```

## Certification

A 7-day pass allows `Production Validated - Staging`. A 14-day pass with representative field operations allows `Production Certified Candidate`.
