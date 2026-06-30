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
| `sahool-platform` | Core Field Platform | 145043 | 537 | `services/sahool-platform/api/main.py` | yes | 8000 | `critical-core-concentration` |
| `sam2-inference` | Field Boundary AI | 580 | 4 | `services/sam2-inference/main.py` | yes | 8080 | `normal` |
| `soil-service` | Soil Intelligence | 698 | 6 | `services/soil-service/main.py` | yes | 8000 | `normal` |
| `supervisor-agent` | Agent Orchestration | 3847 | 10 | `services/supervisor-agent/main.py` | yes | - | `normal` |
| `tts-service` | Voice & Notifications | 595 | 7 | `services/tts-service/main.py` | yes | 8000 | `normal` |
| `vegetation-analysis-service` | Vegetation Analytics | 1539 | 8 | `services/vegetation-analysis-service/main.py` | yes | - | `normal` |
| `video-processor` | Video Processing | 777 | 8 | `services/video-processor/main.py` | yes | 8000 | `normal` |
| `weather-polygon-worker` | Weather Intelligence | 215 | 0 | `services/weather-polygon-worker/src/main.py` | yes | - | `normal` |
| `weather-service` | Weather Intelligence | 60 | 4 | `services/weather-service/main.py` | yes | 8000 | `normal` |
| `weather-signal-engine` | Weather Intelligence | 143 | 0 | `services/weather-signal-engine/src/main.py` | yes | - | `normal` |
