# Unified Platform Catalog (generated — do not edit)

مُصرِّف كتالوج، لا خدمة: يركّب السجلّات القائمة ويكشف تناقضاتها. أعد التوليد بـ
`python scripts/architecture/build_platform_catalog.py`؛ التحقّق بـ`--check`.

- fingerprint: `cc05fa4bd6461efa578b5c98e1e33ab762f88e11e09723cc134deb8909cd1be6`
- components: **34** (backend: 32)
- route rows: **1101** → unique method/path: **989**
- capabilities (derived, uncurated): **849**
- cross-service duplicate method/paths: **14**
- ownership conflicts (incl. TBD/alias): **0**
- UI waivers pending U4 classification: **51**

## Components

| component | type | domain | aliases | tables | wired |
|---|---|---|---|---|---|
| actuator-service | service | execution | sahool-actuator-service | 7 | True |
| agriai-engine | service | simulation-experimental | sahool-agriai-engine | 22 | False |
| ai_agronomist | service | agents | — | 0 | True |
| auth | service | identity | sahool-auth | 0 | True |
| decision-service | service | decision-governance | sahool-decision-service | 42 | True |
| edge-inference | service | edge | — | 0 | True |
| erp-bridge | service | erp-projection | odoo-bridge, sahool-erp-bridge | 15 | True |
| field-management-service | service | fields-internal | — | 33 | True |
| field-segmentation | service | fields-boundary | sahool-field-segmentation | 0 | True |
| frontend | frontend | user-interface | — | 0 | None |
| gis-workflow-service | batch-job-tool | gis-publication | — | 2 | None |
| guardrails-engine | service | decision-governance | sahool-guardrails-engine | 2 | True |
| indicators-service | service | indicators | sahool-indicators-service | 0 | True |
| knowledge-graph | service | knowledge | sahool-knowledge-graph | 0 | True |
| local-ai-rag | service | knowledge | sahool-local-ai-rag | 0 | True |
| mcp_servers | service | agents-mcp | — | 0 | True |
| mobile | mobile | user-interface | — | 0 | None |
| model-registry-adapter | adapter | decision-governance | — | 0 | True |
| qdrant-seed | job | knowledge | sahool-qdrant-seed | 0 | None |
| rag-retrieval | service | knowledge | sahool-rag-retrieval | 2 | True |
| raster-service | service | remote-sensing-truth | sahool-raster-service | 14 | True |
| raster-tiler-service | service | remote-sensing-truth | — | 0 | True |
| remote-sensing-workspace-bff | bff | remote-sensing-workspace | sahool-remote-sensing-workspace-bff | 0 | True |
| sahool-platform | service | platform-core | — | 182 | True |
| sam2-inference | service | fields-boundary | sahool-sam2-inference | 0 | True |
| scout-ingest-service | service | ground-ingest | — | 11 | True |
| soil-service | service | soil | sahool-soil-service | 32 | True |
| supervisor-agent | service | agents | sahool-supervisor-agent | 0 | True |
| tts-service | service | media | sahool-tts-service | 0 | True |
| vegetation-analysis-service | service | vegetation-interpretation | — | 1 | True |
| video-processor | service | media | sahool-video-processor | 0 | True |
| weather-polygon-worker | worker | weather-truth | sahool-weather-polygon-worker | 0 | True |
| weather-service | service | weather-truth | sahool-weather-service | 8 | True |
| weather-signal-engine | worker | weather-truth | sahool-weather-signal-engine | 0 | True |

## Governance gates (U3/U4)

- U3 wiring/ownership: `PASS`
- U4 duplicates/waivers: `PASS`

## Cross-service duplicate method/paths — governed decisions

| method | path | classification | canonical owner | review |
|---|---|---|---|---|
| `GET` | `/` | `service_metadata` | `service-local` | `2026-12-31` |
| `GET` | `/capabilities` | `standard_capability_contract` | `service-local` | `permanent` |
| `GET` | `/contract` | `standard_service_contract` | `service-local` | `permanent` |
| `GET` | `/health` | `standard_health_alias` | `service-local` | `2026-12-31` |
| `GET` | `/healthz` | `standard_liveness` | `service-local` | `permanent` |
| `POST` | `/ingest` | `service_scoped_semantics` | `service-local` | `2026-12-31` |
| `GET` | `/metrics` | `standard_observability` | `service-local` | `permanent` |
| `POST` | `/plan` | `legacy_bff_facade` | `agriai-engine` | `2026-12-31` |
| `GET` | `/products` | `service_scoped_semantics` | `service-local` | `2026-12-31` |
| `POST` | `/query` | `service_scoped_semantics` | `service-local` | `2026-12-31` |
| `GET` | `/readyz` | `standard_readiness` | `service-local` | `permanent` |
| `POST` | `/recommend` | `service_scoped_semantics` | `service-local` | `2026-12-31` |
| `GET` | `/stac` | `legacy_bff_facade` | `raster-service` | `2026-12-31` |
| `GET` | `/stac/collections` | `legacy_bff_facade` | `raster-service` | `2026-12-31` |
