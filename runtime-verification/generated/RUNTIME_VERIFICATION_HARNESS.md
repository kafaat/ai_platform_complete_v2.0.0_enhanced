# SAHOOL Runtime Verification Harness

> Fail-closed plan. Repository discovery never counts as live runtime evidence.

## Summary

- Services: **32**
- Services with probeable endpoints: **27**
- Planned probes: **110**
- Valid live evidence files: **0**
- Runtime verified services: **0**
- Production certified services: **0**

## Evidence contract

Each evidence file must bind the tested Git SHA, immutable live runtime identity, deployment image digest, trusted environment, exact plan hash, timestamps, probe results, and a trusted attestation signature. The harness delegates validation to runtime_evidence_ingestion.py so no weaker parallel acceptance path exists.

## Service probe coverage

| Service | Planned probes | Evidence state |
|---|---:|---|
| actuator-service | 4 | not verified |
| agriai-engine | 4 | not verified |
| ai_agronomist | 6 | not verified |
| auth | 4 | not verified |
| decision-service | 4 | not verified |
| edge-inference | 2 | not verified |
| erp-bridge | 4 | not verified |
| field-management-service | 3 | not verified |
| field-segmentation | 3 | not verified |
| gis-workflow-service | 0 | not verified |
| guardrails-engine | 4 | not verified |
| indicators-service | 3 | not verified |
| knowledge-graph | 3 | not verified |
| local-ai-rag | 3 | not verified |
| mcp_servers | 3 | not verified |
| model-registry-adapter | 1 | not verified |
| qdrant-seed | 0 | not verified |
| rag-retrieval | 3 | not verified |
| raster-service | 3 | not verified |
| raster-tiler-service | 0 | not verified |
| remote-sensing-workspace-bff | 2 | not verified |
| sahool-platform | 17 | not verified |
| sam2-inference | 3 | not verified |
| scout-ingest-service | 2 | not verified |
| soil-service | 5 | not verified |
| supervisor-agent | 7 | not verified |
| tts-service | 4 | not verified |
| vegetation-analysis-service | 7 | not verified |
| video-processor | 3 | not verified |
| weather-polygon-worker | 0 | not verified |
| weather-service | 3 | not verified |
| weather-signal-engine | 0 | not verified |
