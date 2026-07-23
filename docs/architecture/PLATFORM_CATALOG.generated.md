# Unified Platform Catalog (generated — do not edit)

مُصرِّف كتالوج، لا خدمة: يركّب السجلّات القائمة ويكشف تناقضاتها. أعد التوليد بـ
`python scripts/architecture/build_platform_catalog.py`؛ التحقّق بـ`--check`.

- fingerprint: `e7ee8ef2cd0072e69b196acdb607ca270f4cf19a165cff36d0873d46d307b6c1`
- components: **34** (backend: 32)
- route rows: **1094** → unique method/path: **982**
- capabilities (derived, uncurated): **845**
- cross-service duplicate method/paths: **14**
- ownership conflicts (incl. TBD/alias): **1**
- UI waivers pending U4 classification: **50**

## Components

| component | type | domain | aliases | tables | wired |
|---|---|---|---|---|---|
| actuator-service | service | execution | sahool-actuator-service | 7 | True |
| agriai-engine | service | simulation-experimental | sahool-agriai-engine | 22 | True |
| ai_agronomist | service | agents | — | 0 | False |
| auth | service | identity | sahool-auth | 0 | True |
| decision-service | service | decision-governance | sahool-decision-service | 42 | True |
| edge-inference | service | edge | — | 0 | False |
| erp-bridge | service | erp-projection | odoo-bridge, sahool-erp-bridge | 15 | True |
| field-management-service | service | fields-internal | — | 33 | False |
| field-segmentation | service | fields-boundary | sahool-field-segmentation | 0 | True |
| frontend | frontend | user-interface | — | 0 | None |
| gis-workflow-service | batch-job-tool | gis-publication | — | 2 | False |
| guardrails-engine | service | decision-governance | sahool-guardrails-engine | 2 | True |
| indicators-service | service | indicators | sahool-indicators-service | 0 | True |
| knowledge-graph | service | knowledge | sahool-knowledge-graph | 0 | True |
| local-ai-rag | service | knowledge | sahool-local-ai-rag | 0 | True |
| mcp_servers | service | agents-mcp | — | 0 | False |
| mobile | mobile | user-interface | — | 0 | None |
| model-registry-adapter | adapter | decision-governance | — | 0 | False |
| qdrant-seed | job | knowledge | sahool-qdrant-seed | 0 | True |
| rag-retrieval | service | knowledge | sahool-rag-retrieval | 2 | True |
| raster-service | service | remote-sensing-truth | sahool-raster-service | 14 | True |
| raster-tiler-service | service | remote-sensing-truth | — | 0 | False |
| remote-sensing-workspace-bff | bff | remote-sensing-workspace | sahool-remote-sensing-workspace-bff | 0 | True |
| sahool-platform | service | platform-core | — | 182 | True |
| sam2-inference | service | fields-boundary | sahool-sam2-inference | 0 | True |
| scout-ingest-service | service | ground-ingest | — | 11 | False |
| soil-service | service | soil | sahool-soil-service | 32 | True |
| supervisor-agent | service | agents | sahool-supervisor-agent | 0 | True |
| tts-service | service | media | sahool-tts-service | 0 | True |
| vegetation-analysis-service | service | vegetation-interpretation | — | 1 | False |
| video-processor | service | media | sahool-video-processor | 0 | True |
| weather-polygon-worker | worker | weather-truth | sahool-weather-polygon-worker | 0 | False |
| weather-service | service | weather-truth | sahool-weather-service | 8 | True |
| weather-signal-engine | worker | weather-truth | sahool-weather-signal-engine | 0 | False |

## Cross-service duplicate method/paths

- `GET /` ← field-management-service, indicators-service, weather-service
- `GET /capabilities` ← edge-inference, indicators-service
- `GET /contract` ← decision-service, field-management-service, indicators-service, weather-service
- `GET /health` ← actuator-service, agriai-engine, auth, erp-bridge, field-management-service, field-segmentation, guardrails-engine, indicators-service, local-ai-rag, mcp_servers, sam2-inference, soil-service, supervisor-agent, tts-service, vegetation-analysis-service, video-processor, weather-service
- `GET /healthz` ← actuator-service, agriai-engine, ai_agronomist, auth, decision-service, edge-inference, erp-bridge, field-management-service, field-segmentation, guardrails-engine, indicators-service, knowledge-graph, local-ai-rag, mcp_servers, rag-retrieval, raster-service, remote-sensing-workspace-bff, sahool-platform, sam2-inference, scout-ingest-service, soil-service, supervisor-agent, tts-service, vegetation-analysis-service, video-processor, weather-service
- `POST /ingest` ← local-ai-rag, rag-retrieval
- `GET /metrics` ← agriai-engine, ai_agronomist, auth, guardrails-engine, knowledge-graph, rag-retrieval, raster-service, sahool-platform, soil-service, supervisor-agent, tts-service, vegetation-analysis-service
- `POST /plan` ← agriai-engine, sahool-platform
- `GET /products` ← erp-bridge, mcp_servers
- `POST /query` ← ai_agronomist, local-ai-rag
- `GET /readyz` ← actuator-service, agriai-engine, ai_agronomist, auth, decision-service, edge-inference, erp-bridge, field-management-service, field-segmentation, guardrails-engine, indicators-service, knowledge-graph, local-ai-rag, mcp_servers, rag-retrieval, raster-service, remote-sensing-workspace-bff, sahool-platform, sam2-inference, scout-ingest-service, soil-service, supervisor-agent, tts-service, vegetation-analysis-service, video-processor, weather-service
- `POST /recommend` ← agriai-engine, ai_agronomist
- `GET /stac` ← raster-service, sahool-platform
- `GET /stac/collections` ← raster-service, sahool-platform
