# SAHOOL Backend Service Registry v50

> Generated from source code. This registry is the service-boundary baseline for backend ownership, refactoring, CI gates, and future product design.

## Inventory summary

- Services discovered: **26**
- Python LOC discovered: **179,515**
- Routes discovered: **770**
- Largest service concentration: **sahool-platform**
- Protected product decision: **MapHub default must be raw field satellite image / truecolor, not weather and not NDVI-only.**

## Service registry

| Service | Domain | LOC | Routes | Main | Docker | Ports | Risk |
|---|---:|---:|---:|---|---|---|---|
| `actuator-service` | IoT Actuation | 1359 | 6 | `services/actuator-service/main.py` | yes | 8000 | `normal` |
| `agriai-engine` | AI Advisor | 92 | 5 | `services/agriai-engine/main.py` | yes | 8000 | `normal` |
| `ai_agronomist` | AI Advisor | 1581 | 7 | `services/ai_agronomist/main.py` | yes | 8000 | `normal` |
| `auth` | Identity & Access | 2202 | 27 | `services/auth/main.py` | yes | 8000 | `normal` |
| `edge-inference` | Edge Inference | 1138 | 5 | `services/edge-inference/main.py` | no | - | `medium-runtime-contract-gap` |
| `field-segmentation` | Field Boundary AI | 613 | 4 | `services/field-segmentation/main.py` | yes | 8000 | `normal` |
| `guardrails-engine` | AI Safety & Governance | 1900 | 7 | `services/guardrails-engine/main.py` | yes | 8000 | `normal` |
| `indicators-service` | Vegetation Analytics | 51 | 4 | `services/indicators-service/main.py` | yes | - | `normal` |
| `knowledge-graph` | Edge Inference | 102 | 7 | `services/knowledge-graph/main.py` | yes | 8000 | `normal` |
| `local-ai-rag` | Knowledge Retrieval | 594 | 5 | `services/local-ai-rag/main.py` | yes | 8000 | `normal` |
| `mcp_servers` | Agent Tools | 2249 | 32 | `-` | yes | 8000 | `medium-runtime-contract-gap` |
| `odoo-bridge` | ERP Integration | 1876 | 10 | `services/odoo-bridge/main.py` | yes | 8126 | `normal` |
| `qdrant-seed` | Unclassified / Support | 997 | 0 | `-` | yes | - | `medium-runtime-contract-gap` |
| `rag-retrieval` | Knowledge Retrieval | 106 | 5 | `services/rag-retrieval/main.py` | yes | 8000 | `normal` |
| `raster-service` | Imagery & Raster | 11158 | 62 | `services/raster-service/main.py` | yes | 8001 | `high-boundary-pressure` |
| `raster-tiler-service` | Imagery & Raster | 0 | 0 | `-` | yes | 8088 | `medium-runtime-contract-gap` |
| `sahool-platform` | Core Field Platform | 144999 | 537 | `services/sahool-platform/api/main.py` | yes | 8000 | `critical-core-concentration` |
| `sam2-inference` | Field Boundary AI | 580 | 4 | `services/sam2-inference/main.py` | yes | 8080 | `normal` |
| `soil-service` | Soil Intelligence | 698 | 6 | `services/soil-service/main.py` | yes | 8000 | `normal` |
| `supervisor-agent` | Agent Orchestration | 3847 | 10 | `services/supervisor-agent/main.py` | yes | - | `normal` |
| `tts-service` | Voice & Notifications | 595 | 7 | `services/tts-service/main.py` | yes | 8000 | `normal` |
| `vegetation-analysis-service` | Vegetation Analytics | 1539 | 8 | `services/vegetation-analysis-service/main.py` | yes | - | `normal` |
| `video-processor` | Video Processing | 777 | 8 | `services/video-processor/main.py` | yes | 8000 | `normal` |
| `weather-polygon-worker` | Weather Intelligence | 215 | 0 | `services/weather-polygon-worker/src/main.py` | yes | - | `normal` |
| `weather-service` | Weather Intelligence | 60 | 4 | `services/weather-service/main.py` | yes | 8000 | `normal` |
| `weather-signal-engine` | Weather Intelligence | 143 | 0 | `services/weather-signal-engine/src/main.py` | yes | - | `normal` |

## Domain ownership matrix

| Domain | Services | Current role | Recommended ownership rule |
|---|---:|---|---|
| AI Advisor | 2 | Agronomic chat runtime and field-memory evidence grounding. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| AI Safety & Governance | 1 | Guardrails, prompt-safety, policy tiers, answer governance. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| Agent Orchestration | 1 | Supervisor-agent planning/skill execution. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| Agent Tools | 1 | MCP tool layer and agent-callable skills. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| Core Field Platform | 1 | Core field/farm/season/tasks/recommendation API surface and many cross-domain routes. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| ERP Integration | 1 | Odoo bridge and business system integration. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| Edge Inference | 2 | Edge/vision runtime support. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| Field Boundary AI | 2 | Segmentation and boundary extraction inference. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| Identity & Access | 1 | Support service. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| Imagery & Raster | 2 | Satellite scenes, COG/tile readiness, historical imagery timeline, CDSE backfill, TileJSON. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| IoT Actuation | 1 | Actuator command/control domain. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| Knowledge Retrieval | 2 | RAG/query retrieval layer for documents and advice grounding. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| Soil Intelligence | 1 | Soil/lab context and tenant-scoped soil operations. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| Unclassified / Support | 1 | Support/runtime utilities requiring explicit ownership. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| Vegetation Analytics | 2 | NDVI/NDMI/NDRE and crop-vigor derived analytics. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| Video Processing | 1 | Video inference/processing pipeline. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| Voice & Notifications | 1 | TTS and voice response infrastructure. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |
| Weather Intelligence | 3 | Forecast/history/weather tiles, wind direction fallback, operation windows, risk signals. | One product owner, one API contract, explicit data-source ownership, and CI smoke per domain. |

## Immediate architecture decisions

1. **Create Field Intelligence Backbone**: a thin aggregation/orchestration layer that composes field profile, raw truecolor imagery, indices, weather history, events, zones, alerts, recommendations, and AI evidence without moving all domain logic into one service.
2. **Keep raw imagery first**: truecolor field imagery is the default operator view; NDVI/NDMI are interpretation overlays and should be opt-in or preserved from explicit user choice.
3. **Separate job lifecycle from tile rendering**: backfill jobs need status/progress/retry semantics independent of tile serving.
4. **Treat AI as an evidence client**: AI should consume context packs and evidence references; it should not become the owner of field, imagery, weather, or operations data.
5. **Reduce sahool-platform concentration by seams, not by random splitting**: extract stable capabilities only after contract tests exist.

## Recommended next services / capabilities

| Proposed capability | Why it matters | Source-aligned inspiration | First implementation step |
|---|---|---|---|
| `field-intelligence-service` | Single evidence-backed context for field decisions. | Data Manager style agricultural data model + FieldView field health + Xarvio stage/weather/image reasoning. | Add read-only `/field-intelligence/analyze` composer backed by existing services. |
| `imagery-job-service` | Turns historical backfill into a visible, retryable operation. | Enterprise async job lifecycle used by geospatial/data platforms. | Persist `job_id`, status, counters, scene errors, and retry contract. |
| `productivity-zones-service` | Converts imagery history into stable management zones. | EOSDA-style zoning and VRA workflows. | Generate zones from multi-date NDVI/NDMI quantiles and expose GeoJSON. |
| `operation-window-service` | Converts weather into safe spray/harvest/sowing/fertilizer windows. | Xarvio/CropX-style weather-aware operation planning. | Produce per-field hourly suitability with limiting factors. |
| `recommendation-lifecycle-service` | Moves advice from text to draft/review/approve/execute/learn. | Deere/Agworld work-plan and collaboration patterns. | Add recommendation states and audit events. |
| `machine-workplan-export-service` | Converts prescriptions into equipment/export formats. | John Deere Operations Center work plans. | Add adapter abstraction, start with neutral GeoJSON/CSV. |
| `data-quality-service` | Explains missing tiles/weather/sensors and confidence. | Enterprise agronomy platforms surface data coverage and quality. | Add `/data-quality/field/{id}` with coverage badges. |

## CI guardrails to add next

- Static guard: MapHub default remains raw satellite/truecolor, never weather, never NDVI-only.
- Static guard: every new backend service must appear in `SERVICE_REGISTRY.md`.
- Contract guard: every external connector declares timeout, circuit breaker, user-agent/key requirements, and fail-safe behavior.
- Domain guard: new routes in `sahool-platform` over a size threshold require ownership note or extraction plan.
