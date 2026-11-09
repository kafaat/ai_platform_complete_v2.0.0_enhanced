# SAHOOL Backend Service Registry

> Generated automatically from source code by `scripts/ci/generate_service_inventory.py`.
> Do not hand-edit counts; run the generator and commit the generated inventory files.

## Inventory summary

- Services discovered: **33**
- Python LOC discovered: **311,069**
- Routes discovered: **1135**
- Largest service concentration: **sahool-platform**
- Protected product decision: **MapHub default must be raw field satellite image / truecolor, not weather and not NDVI-only.**

## Service registry

| Service | Domain | Python files | LOC | Tests | Routes | Main | Docker | Requirements | Risk |
|---|---:|---:|---:|---:|---:|---|---|---|---|
| `actuator-service` | IoT Actuation | 14 | 3367 | 6 | 7 | `services/actuator-service/main.py` | `services/actuator-service/Dockerfile` | `services/actuator-service/requirements.txt` | `normal` |
| `agriai-engine` | AI Advisor | 18 | 2723 | 5 | 9 | `services/agriai-engine/main.py` | `services/agriai-engine/Dockerfile` | `services/agriai-engine/requirements.txt` | `normal` |
| `ai_agronomist` | AI Advisor | 46 | 6899 | 1 | 13 | `services/ai_agronomist/main.py` | `services/ai_agronomist/Dockerfile` | `services/ai_agronomist/requirements.txt` | `normal` |
| `auth` | Identity & Access | 22 | 2668 | 2 | 29 | `services/auth/main.py` | `services/auth/Dockerfile` | `services/auth/requirements.txt` | `normal` |
| `decision-service` | Decision SoR | 88 | 21399 | 66 | 72 | `services/decision-service/main.py` | `services/decision-service/Dockerfile` | `services/decision-service/requirements.txt` | `normal` |
| `edge-inference` | Edge Inference | 12 | 1700 | 2 | 7 | `services/edge-inference/main.py` | `services/edge-inference/Dockerfile.arm64` | `services/edge-inference/requirements.txt` | `normal` |
| `field-management-service` | Unclassified / Support | 3 | 527 | 2 | 7 | `services/field-management-service/main.py` | `services/field-management-service/Dockerfile` | `services/field-management-service/requirements.txt` | `normal` |
| `field-segmentation` | Field Boundary AI | 5 | 1049 | 2 | 4 | `services/field-segmentation/main.py` | `services/field-segmentation/Dockerfile` | `services/field-segmentation/requirements.txt` | `normal` |
| `gis-workflow-service` | Unclassified / Support | 22 | 1785 | 11 | 0 | `-` | `-` | `services/gis-workflow-service/requirements.txt` | `medium-runtime-contract-gap` |
| `guardrails-engine` | AI Safety & Governance | 14 | 1899 | 1 | 9 | `services/guardrails-engine/main.py` | `services/guardrails-engine/Dockerfile` | `services/guardrails-engine/requirements.txt` | `normal` |
| `indicators-service` | Vegetation Analytics | 8 | 1151 | 4 | 12 | `services/indicators-service/main.py` | `services/indicators-service/Dockerfile` | `services/indicators-service/requirements.txt` | `normal` |
| `knowledge-graph` | Edge Inference | 3 | 402 | 1 | 7 | `services/knowledge-graph/main.py` | `services/knowledge-graph/Dockerfile` | `services/knowledge-graph/requirements.txt` | `normal` |
| `local-ai-rag` | Knowledge Retrieval | 3 | 916 | 1 | 5 | `services/local-ai-rag/main.py` | `services/local-ai-rag/Dockerfile` | `services/local-ai-rag/requirements.txt` | `normal` |
| `mcp_servers` | Agent Tools | 12 | 2254 | 1 | 34 | `-` | `services/mcp_servers/Dockerfile` | `services/mcp_servers/requirements.txt` | `normal` |
| `model-registry-adapter` | Unclassified / Support | 8 | 1658 | 3 | 0 | `-` | `services/model-registry-adapter/Dockerfile` | `-` | `medium-runtime-contract-gap` |
| `odoo-bridge` | ERP Integration | 11 | 1963 | 2 | 11 | `services/odoo-bridge/main.py` | `services/odoo-bridge/Dockerfile` | `services/odoo-bridge/requirements.txt` | `normal` |
| `qdrant-seed` | Unclassified / Support | 5 | 1174 | 1 | 0 | `-` | `services/qdrant-seed/Dockerfile` | `services/qdrant-seed/requirements.txt` | `medium-runtime-contract-gap` |
| `rag-retrieval` | Knowledge Retrieval | 5 | 826 | 1 | 5 | `services/rag-retrieval/main.py` | `services/rag-retrieval/Dockerfile` | `services/rag-retrieval/requirements.txt` | `normal` |
| `raster-service` | Imagery & Raster | 217 | 37927 | 114 | 86 | `services/raster-service/main.py` | `services/raster-service/Dockerfile` | `services/raster-service/requirements.txt` | `normal` |
| `raster-tiler-service` | Imagery & Raster | 2 | 233 | 1 | 2 | `services/raster-tiler-service/main.py` | `services/raster-tiler-service/Dockerfile` | `services/raster-tiler-service/requirements.txt` | `normal` |
| `realtime-agent` | Unclassified / Support | 16 | 1649 | 7 | 0 | `services/realtime-agent/main.py` | `services/realtime-agent/Dockerfile` | `services/realtime-agent/requirements.txt` | `medium-runtime-contract-gap` |
| `realtime-session` | Unclassified / Support | 12 | 1306 | 1 | 7 | `services/realtime-session/main.py` | `services/realtime-session/Dockerfile` | `services/realtime-session/requirements.txt` | `normal` |
| `remote-sensing-workspace-bff` | Unclassified / Support | 2 | 480 | 1 | 3 | `services/remote-sensing-workspace-bff/main.py` | `services/remote-sensing-workspace-bff/Dockerfile` | `services/remote-sensing-workspace-bff/requirements.txt` | `normal` |
| `sahool-platform` | Core Field Platform | 1185 | 184560 | 501 | 639 | `services/sahool-platform/api/main.py` | `services/sahool-platform/Dockerfile` | `-` | `critical-core-concentration` |
| `sam2-inference` | Field Boundary AI | 4 | 1204 | 1 | 4 | `services/sam2-inference/main.py` | `services/sam2-inference/Dockerfile` | `services/sam2-inference/requirements.txt` | `normal` |
| `scout-ingest-service` | Unclassified / Support | 7 | 2464 | 3 | 22 | `services/scout-ingest-service/main.py` | `services/scout-ingest-service/Dockerfile` | `services/scout-ingest-service/requirements.txt` | `normal` |
| `soil-service` | Soil Intelligence | 54 | 6827 | 19 | 60 | `services/soil-service/main.py` | `services/soil-service/Dockerfile` | `services/soil-service/requirements.txt` | `normal` |
| `supervisor-agent` | Agent Orchestration | 23 | 3778 | 8 | 11 | `services/supervisor-agent/main.py` | `services/supervisor-agent/Dockerfile` | `services/supervisor-agent/requirements.txt` | `normal` |
| `tts-service` | Voice & Notifications | 10 | 1465 | 1 | 8 | `services/tts-service/main.py` | `services/tts-service/Dockerfile` | `services/tts-service/requirements.txt` | `normal` |
| `vegetation-analysis-service` | Vegetation Analytics | 45 | 4830 | 19 | 22 | `services/vegetation-analysis-service/main.py` | `services/vegetation-analysis-service/Dockerfile` | `services/vegetation-analysis-service/requirements.txt` | `normal` |
| `video-processor` | Video Processing | 9 | 1088 | 1 | 11 | `services/video-processor/main.py` | `services/video-processor/Dockerfile` | `services/video-processor/requirements.txt` | `normal` |
| `weather-service` | Weather Intelligence | 50 | 8611 | 31 | 29 | `services/weather-service/main.py` | `services/weather-service/Dockerfile` | `services/weather-service/requirements.txt` | `normal` |
| `weather-signal-engine` | Weather Intelligence | 2 | 287 | 0 | 0 | `services/weather-signal-engine/src/main.py` | `services/weather-signal-engine/Dockerfile` | `services/weather-signal-engine/requirements.txt` | `medium-runtime-contract-gap` |

## Domain ownership matrix

| Domain | Services | Recommended ownership rule |
|---|---:|---|
| AI Advisor | `agriai-engine`, `ai_agronomist` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| AI Safety & Governance | `guardrails-engine` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Agent Orchestration | `supervisor-agent` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Agent Tools | `mcp_servers` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Core Field Platform | `sahool-platform` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Decision SoR | `decision-service` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| ERP Integration | `odoo-bridge` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Edge Inference | `edge-inference`, `knowledge-graph` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Field Boundary AI | `field-segmentation`, `sam2-inference` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Identity & Access | `auth` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Imagery & Raster | `raster-service`, `raster-tiler-service` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| IoT Actuation | `actuator-service` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Knowledge Retrieval | `local-ai-rag`, `rag-retrieval` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Soil Intelligence | `soil-service` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Unclassified / Support | `field-management-service`, `gis-workflow-service`, `model-registry-adapter`, `qdrant-seed`, `realtime-agent`, `realtime-session`, `remote-sensing-workspace-bff`, `scout-ingest-service` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Vegetation Analytics | `indicators-service`, `vegetation-analysis-service` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Video Processing | `video-processor` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Voice & Notifications | `tts-service` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |
| Weather Intelligence | `weather-service`, `weather-signal-engine` | One product owner, one API contract, explicit data-source ownership, CI smoke, and generated registry drift guard. |

## Governance rules

1. `SERVICE_REGISTRY.md`, `service_inventory.generated.json`, and `route_inventory.generated.json` are generated from code.
2. CI must fail when generated inventory differs from committed inventory.
3. Services with routes and zero tests are `high-zero-test-routes` until a smoke/contract test exists.
4. `docker-compose.v9.yml` is the only stack definition; the former alternates (`fixed`/`unified`/`light`) live in `docs/history/compose/`, and every other tracked compose file is a declared overlay/test stack/companion in `docs/architecture/compose_file_roster.json` (enforced by `scripts/ci/compose_roster_guard.py`).
5. `sahool-platform` hosts the Field Intelligence Backbone (see `docs/backend/ADR_V50_BACKEND_OWNERSHIP_AND_RAW_IMAGERY_DEFAULT.md`).
