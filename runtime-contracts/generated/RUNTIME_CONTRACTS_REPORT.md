# SAHOOL Runtime Contract Inventory

> Static repository evidence only. This report does not prove live runtime behavior.

## Summary

- Services: **32**
- Health contract: **27**
- Readiness contract: **26**
- Metrics endpoint or instrumentation: **13**
- Tracing instrumentation: **4**
- Declared configuration/secrets: **30**
- Complete static contracts: **2**
- Live runtime verified: **0**

## Per-service completeness

| Service | Score | Health | Ready | Metrics | Tracing | Config |
|---|---:|:---:|:---:|:---:|:---:|:---:|
| actuator-service | 100.0% | ✓ | ✓ | ✓ | ✓ | ✓ |
| agriai-engine | 85.7% | ✓ | ✓ | ✓ | — | ✓ |
| ai_agronomist | 85.7% | ✓ | ✓ | ✓ | — | ✓ |
| auth | 85.7% | ✓ | ✓ | ✓ | — | ✓ |
| decision-service | 71.4% | ✓ | ✓ | — | — | ✓ |
| edge-inference | 71.4% | ✓ | ✓ | — | — | ✓ |
| erp-bridge | 71.4% | ✓ | ✓ | — | — | ✓ |
| field-management-service | 71.4% | ✓ | ✓ | — | — | ✓ |
| field-segmentation | 71.4% | ✓ | ✓ | — | — | ✓ |
| gis-workflow-service | 0.0% | — | — | — | — | — |
| guardrails-engine | 85.7% | ✓ | ✓ | ✓ | — | ✓ |
| indicators-service | 71.4% | ✓ | ✓ | — | — | ✓ |
| knowledge-graph | 85.7% | ✓ | ✓ | ✓ | — | ✓ |
| local-ai-rag | 85.7% | ✓ | ✓ | — | ✓ | ✓ |
| mcp_servers | 71.4% | ✓ | ✓ | — | ✓ | ✓ |
| model-registry-adapter | 42.9% | ✓ | — | — | — | ✓ |
| qdrant-seed | 28.6% | — | — | — | — | ✓ |
| rag-retrieval | 85.7% | ✓ | ✓ | ✓ | — | ✓ |
| raster-service | 85.7% | ✓ | ✓ | ✓ | — | ✓ |
| raster-tiler-service | 28.6% | — | — | — | — | — |
| remote-sensing-workspace-bff | 71.4% | ✓ | ✓ | — | — | ✓ |
| sahool-platform | 85.7% | ✓ | ✓ | ✓ | — | ✓ |
| sam2-inference | 71.4% | ✓ | ✓ | — | — | ✓ |
| scout-ingest-service | 71.4% | ✓ | ✓ | — | — | ✓ |
| soil-service | 85.7% | ✓ | ✓ | ✓ | — | ✓ |
| supervisor-agent | 85.7% | ✓ | ✓ | ✓ | — | ✓ |
| tts-service | 85.7% | ✓ | ✓ | ✓ | — | ✓ |
| vegetation-analysis-service | 100.0% | ✓ | ✓ | ✓ | ✓ | ✓ |
| video-processor | 71.4% | ✓ | ✓ | — | — | ✓ |
| weather-polygon-worker | 42.9% | — | — | — | — | ✓ |
| weather-service | 71.4% | ✓ | ✓ | — | — | ✓ |
| weather-signal-engine | 42.9% | — | — | — | — | ✓ |

## Interpretation

A missing static signal is a repository gap or an extraction limitation. A present signal is not production proof; live certification still requires observed responses, telemetry, and deployment evidence.
