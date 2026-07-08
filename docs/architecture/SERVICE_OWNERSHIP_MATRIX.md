# Service Ownership Matrix — P0 Boundary Contract

This matrix defines the intended ownership boundary used by the platform anti-bloat guards. It is intentionally conservative: `sahool-platform` remains a BFF/orchestrator while domain computation moves behind service contracts.

| Service | Type | Owns | Consumes | Emits | Forbidden ownership |
|---|---|---|---|---|---|
| `actuator-service` | `execution-adapter` | device/actuator command dispatch<br>execution adapter logs | TBD | TBD | agronomic decision making |
| `agriai-engine` | `decision-compute` | planning/replay<br>recommendation scoring<br>simulation | TBD | TBD | device execution or policy approval |
| `erp-bridge` | `adapter` | Odoo/ERP sync<br>external adapter state | TBD | TBD | internal agronomic truth |
| `field-management-service` | `system-of-record-target` | farms<br>field lifecycle target ownership<br>fields<br>geometry<br>zones | TBD | TBD | raster/weather computation |
| `guardrails-engine` | `policy-engine` | approval gates<br>policy validation<br>safety constraints | TBD | TBD | recommendation generation |
| `knowledge-graph` | `knowledge-store` | evidence graph target<br>knowledge graph nodes/edges | TBD | TBD | operational source of truth |
| `rag-retrieval` | `knowledge-retrieval` | document ingest/search<br>retrieval context | TBD | TBD | decision records |
| `raster-service` | `compute-store` | COG assets<br>imagery dates<br>terrain raster products<br>tiles<br>vegetation indices | TBD | TBD | agronomic decisions |
| `sahool-platform` | `bff-orchestrator` | BFF views<br>legacy compatibility facades<br>light orchestration<br>tenant/auth context propagation | TBD | TBD | new domain compute, direct raster/weather/AI business logic |
| `soil-service` | `system-of-record` | soil readings<br>soil sample planning target<br>soil suitability | TBD | TBD | satellite imagery processing |
| `weather-service` | `system-of-record` | forecast/history contracts<br>operation windows after extraction<br>weather signals | TBD | TBD | decision approval or execution |
