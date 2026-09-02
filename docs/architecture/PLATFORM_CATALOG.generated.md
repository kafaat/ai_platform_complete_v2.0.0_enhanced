# Unified Platform Catalog (generated — do not edit)

مُصرِّف كتالوج، لا خدمة: يركّب السجلّات القائمة ويكشف تناقضاتها. أعد التوليد بـ
`python scripts/architecture/build_platform_catalog.py`؛ التحقّق بـ`--check`.

- fingerprint: `b2cb946fcd9020f9409cea1c7152a369a8e15708342689aea196693142f74948`
- components: **36** (backend: 32)
- route rows: **1112** → unique method/path: **998**
- capabilities (derived, uncurated): **827**
- cross-service duplicate method/paths: **12**
- ownership conflicts (incl. TBD/alias): **0**
- UI waivers pending U4 classification: **52**

## Components

| component | type | domain | aliases | tables | wired |
|---|---|---|---|---|---|
| actuator-service | service | execution | sahool-actuator-service | 7 | True |
| agriai-engine | service | simulation-experimental | sahool-agriai-engine | 21 | False |
| ai_agronomist | service | agents | sahool-ai-agronomist | 0 | True |
| auth | service | identity | sahool-auth | 0 | True |
| decision-service | service | decision-governance | sahool-decision-service | 42 | True |
| edge-inference | service | edge | sahool-edge | 0 | True |
| erp-bridge | service | erp-projection | odoo-bridge, sahool-erp-bridge | 15 | True |
| field-management-service | service | fields-internal | sahool-field-management | 32 | True |
| field-segmentation | service | fields-boundary | sahool-field-segmentation | 0 | True |
| frontend | frontend | user-interface | sahool-frontend | 0 | None |
| gis-workflow-service | tool_bundle | gis-publication | — | 2 | None |
| guardrails-engine | service | decision-governance | sahool-guardrails-engine | 2 | True |
| indicators-service | service | indicators | sahool-indicators-service | 0 | True |
| knowledge-graph | service | knowledge | sahool-knowledge-graph | 0 | True |
| local-ai-rag | service | knowledge | sahool-local-ai-rag | 0 | True |
| mcp_servers | service | agents-mcp | sahool-market-mcp, sahool-sentinel-hub-mcp, sahool-weather-mcp, sahool-wofost-mcp | 0 | True |
| mobile | mobile | user-interface | — | 0 | None |
| model-registry-adapter | worker_adapter | decision-governance | sahool-model-lifecycle-adapter | 0 | True |
| notification-agent | worker | notifications | sahool-notification-agent | 0 | None |
| qdrant-seed | init_job | knowledge | sahool-qdrant-seed | 0 | None |
| rag-retrieval | service | knowledge | sahool-rag-retrieval | 2 | True |
| raster-service | service | remote-sensing-truth | sahool-raster-backfill-scan-worker, sahool-raster-cache-invalidation-worker, sahool-raster-service | 13 | True |
| raster-tiler-service | service | remote-sensing-truth | — | 0 | True |
| remote-sensing-workspace-bff | bff | remote-sensing-workspace | sahool-remote-sensing-workspace-bff | 0 | True |
| sahool-platform | service | platform-core | sahool-actuator-dispatch-worker, sahool-canonical-execution-learning-worker, sahool-irrigation-reservation-lifecycle-worker, sahool-model-registry-worker, sahool-phase-runtime-outbox-worker, sahool-plugin-runtime-worker, sahool-reservation-dispatch-relay-worker, sahool-water-ledger-worker | 195 | True |
| sam2-inference | service | fields-boundary | sahool-sam2-inference | 0 | True |
| scout-ingest-service | service | ground-ingest | sahool-scout-ingest, sahool-scout-ingest-projection | 11 | True |
| soil-service | service | soil | sahool-soil-service | 32 | True |
| supervisor-agent | service | agents | sahool-supervisor-agent | 0 | True |
| telegram-bot | service | messaging-channel | sahool-telegram-bot | 0 | None |
| tts-service | service | media | sahool-tts-service | 0 | True |
| vegetation-analysis-service | service | vegetation-interpretation | sahool-vegetation-analysis | 1 | True |
| video-processor | service | media | sahool-video-processor | 0 | True |
| weather-polygon-worker | worker | weather-truth | sahool-weather-polygon-worker | 0 | True |
| weather-service | service | weather-truth | sahool-weather-service | 8 | True |
| weather-signal-engine | worker | weather-truth | sahool-weather-signal-engine | 0 | True |

## Architecture gates

- ARCH-S1a component classification: `PASS`
- ARCH-S2 dependency truth: `PASS` — edges **804**
- S2 relations: CALLS=38, CONSUMES=1, EMITS=1, READS=413, ROUTES_TO=70, WRITES=281

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
| `GET` | `/metrics` | `standard_observability` | `service-local` | `permanent` |
| `GET` | `/readyz` | `standard_readiness` | `service-local` | `permanent` |
| `GET` | `/runtime-identity` | `standard_observability` | `service-local` | `permanent` |
| `POST` | `/v1/ingest` | `service_scoped_semantics` | `service-local` | `2026-12-31` |
| `GET` | `/v1/products` | `service_scoped_semantics` | `service-local` | `2026-12-31` |
| `POST` | `/v1/query` | `service_scoped_semantics` | `service-local` | `2026-12-31` |
| `POST` | `/v1/recommend` | `service_scoped_semantics` | `service-local` | `2026-12-31` |
