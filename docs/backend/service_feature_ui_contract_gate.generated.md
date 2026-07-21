# service-feature-ui-contract-gate report

- services: 32
- passed: 32
- failed: 0

## Service evidence

### `auth` — pass
classification: `ui`
- ui: 49 match(es)
  - `frontend/src/App.tsx` ← `LoginPage`
  - `frontend/src/App.tsx` ← `SignupPage`
  - `frontend/src/components/maphub/ImageryAutoRefreshGuard.static.test.ts` ← `refresh`
  - `frontend/src/components/fieldview/NdviUnavailableNotice.tsx` ← `refresh`
  - `frontend/src/sections/MapHubTwoYearBackfill.static.test.ts` ← `refresh`
- gateway: 8 match(es)
  - `nginx/nginx.unified.conf` ← `/auth/`
  - `nginx/nginx.unified.conf` ← `auth_backend`
  - `nginx/nginx.light.conf` ← `/auth/`
  - `nginx/nginx.light.conf` ← `auth_backend`
  - `nginx/nginx.fixed.conf` ← `/auth/`

### `sahool-platform` — pass
classification: `ui`
- ui: 205 match(es)
  - `frontend/src/config/backendCoverageRegistry.ts` ← `/api/v1`
  - `frontend/src/config/backendCoverageRegistry.test.ts` ← `/api/v1`
  - `frontend/src/components/AddFieldWithMap.tsx` ← `/api/v1`
  - `frontend/src/components/AddFieldWithMap.tsx` ← `AddFieldWithMap`
  - `frontend/src/components/AddFieldWithMap.undoredo.test.tsx` ← `AddFieldWithMap`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf` ← `/api/v1/`
  - `nginx/nginx.fixed.conf` ← `platform_backend`
  - `nginx/nginx.v9.conf` ← `/api/v1/`
  - `nginx/nginx.v9.conf` ← `platform_backend`

### `raster-service` — pass
classification: `ui`
- ui: 24 match(es)
  - `frontend/src/components/FieldIndicatorMap.static.test.ts` ← `FieldIndicatorMap`
  - `frontend/src/components/FieldIndicatorMap.tsx` ← `cdse-tilejson`
  - `frontend/src/components/FieldIndicatorMap.tsx` ← `tilejson`
  - `frontend/src/components/FieldIndicatorMap.tsx` ← `FieldIndicatorMap`
  - `frontend/src/components/fieldhealth/ScoutingMap.tsx` ← `FieldIndicatorMap`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf` ← `/api/raster/`
  - `nginx/nginx.fixed.conf` ← `raster_backend`
  - `nginx/nginx.v9.conf` ← `/api/raster/`
  - `nginx/nginx.v9.conf` ← `raster_backend`

### `vegetation-analysis-service` — pass
classification: `ui`
- ui: 98 match(es)
  - `frontend/src/App.tsx` ← `FieldRanking`
  - `frontend/src/config/endpoints.ts` ← `vegetation`
  - `frontend/src/components/NDVIGauge.tsx` ← `NDVI`
  - `frontend/src/components/ds/tokens.ts` ← `NDVI`
  - `frontend/src/components/fieldhealth/index.ts` ← `NDVI`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf` ← `/api/vegetation/`
  - `nginx/nginx.fixed.conf` ← `vegetation_backend`
  - `nginx/nginx.v9.conf` ← `/api/vegetation/`
  - `nginx/nginx.v9.conf` ← `vegetation_backend`

### `indicators-service` — pass
classification: `ui`
- ui: 30 match(es)
  - `frontend/src/App.tsx` ← `HybridIndexPage`
  - `frontend/src/App.tsx` ← `indicators`
  - `frontend/src/config/endpoints.ts` ← `indicators`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts` ← `indicators`
  - `frontend/src/components/insights/MapIndicatorLegend.test.tsx` ← `indicators`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf` ← `/api/indicators/`
  - `nginx/nginx.fixed.conf` ← `indicators_backend`
  - `nginx/nginx.v9.conf` ← `/api/indicators/`
  - `nginx/nginx.v9.conf` ← `indicators_backend`

### `weather-service` — pass
classification: `ui`
- ui: 16 match(es)
  - `frontend/src/App.tsx` ← `WeatherAdvice`
  - `frontend/src/components/maphub/weather/README.md` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/README.md` ← `WeatherProbePopup`
  - `frontend/src/components/maphub/weather/WeatherActionLifecycle.static.test.ts` ← `WeatherProbePopup`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts` ← `WeatherTileLayer`
- platform-proxy: 300 match(es)
  - `services/sahool-platform/core/skills_registry.py` ← `weather`
  - `services/sahool-platform/core/gdd_phenology.py` ← `weather-service`
  - `services/sahool-platform/core/gdd_phenology.py` ← `weather`
  - `services/sahool-platform/core/weather_overlay_pipeline.py` ← `weather`
  - `services/sahool-platform/core/field_intelligence_card.py` ← `weather`

### `soil-service` — pass
classification: `ui`
- ui: 154 match(es)
  - `frontend/src/App.tsx` ← `soil`
  - `frontend/src/config/endpoints.ts` ← `soil`
  - `frontend/src/config/backendCoverageRegistry.ts` ← `soil`
  - `frontend/src/config/backendCoverageRegistry.ts` ← `Soil`
  - `frontend/src/components/AddFieldWithMap.tsx` ← `soil`
- platform-proxy: 283 match(es)
  - `services/sahool-platform/README.md` ← `soil`
  - `services/sahool-platform/knowledge/conservative_rag.py` ← `soil`
  - `services/sahool-platform/core/skills_registry.py` ← `soil`
  - `services/sahool-platform/core/historical_onboarding.py` ← `soil`
  - `services/sahool-platform/core/crop_rotation_intelligence.py` ← `soil`

### `field-segmentation` — pass
classification: `ui`
- ui: 7 match(es)
  - `frontend/src/components/AddFieldWithMap.tsx` ← `segmentField`
  - `frontend/src/components/AddFieldWithMap.tsx` ← `AutoSegmentControl`
  - `frontend/src/components/maphub/AutoSegmentControl.tsx` ← `AutoSegmentControl`
  - `frontend/src/services/api.test.ts` ← `segmentField`
  - `frontend/src/services/api.test.ts` ← `/api/segmentation`
- platform-proxy: 8 match(es)
  - `services/sahool-platform/api/field_geometry_save_guard.py` ← `segmentation`
  - `services/sahool-platform/api/routers/service_proxy.py` ← `SEGMENTATION_URL`
  - `services/sahool-platform/api/routers/service_proxy.py` ← `/api/segmentation/`
  - `services/sahool-platform/api/routers/service_proxy.py` ← `segmentation`
  - `services/sahool-platform/tests/test_p0_5_decision_sor_final_certification_guard.py` ← `/api/segmentation/`

### `sam2-inference` — pass
classification: `internal`
- internal-consumer: 33 match(es)
  - `services/field-segmentation/exg_preprocess.py` ← `sam2`
  - `services/field-segmentation/test_segmentation.py` ← `SEGMENTATION_INFERENCE_URL`
  - `services/field-segmentation/test_segmentation.py` ← `SEGMENTATION_BACKEND`
  - `services/field-segmentation/test_segmentation.py` ← `sam2`
  - `services/field-segmentation/test_exg_preprocess.py` ← `sam2`

### `ai_agronomist` — pass
classification: `ui`
- ui: 18 match(es)
  - `frontend/src/App.tsx` ← `ChatbotPage`
  - `frontend/src/sections/ChatbotPage.tsx` ← `ChatbotPage`
  - `frontend/src/sections/ChatbotPage.tsx` ← `ai-agronomist`
  - `frontend/src/sections/ChatbotAiEvidenceTransparency.static.test.ts` ← `ChatbotPage`
  - `frontend/src/sections/ChatbotApprovalUi.v58.static.test.ts` ← `ChatbotPage`
- gateway: 2 match(es)
  - `nginx/nginx.v9.conf` ← `/api/ai-agronomist/`
  - `nginx/nginx.v9.conf` ← `ai_agronomist_backend`

### `rag-retrieval` — pass
classification: `internal-sensitive`
- internal-consumer: 16 match(es)
  - `services/ai_agronomist/ai_evidence_runtime.py` ← `RAG_BASE_URL`
  - `services/ai_agronomist/ai_evidence_runtime.py` ← `rag-retrieval`
  - `services/ai_agronomist/main.py` ← `RAG_BASE_URL`
  - `services/ai_agronomist/main.py` ← `rag-retrieval`
  - `tests_v9/test_service_feature_ui_contract_gate.py` ← `rag-retrieval`

### `knowledge-graph` — pass
classification: `internal-sensitive`
- internal-consumer: 20 match(es)
  - `services/ai_agronomist/ai_evidence_runtime.py` ← `KNOWLEDGE_GRAPH_URL`
  - `services/ai_agronomist/ai_evidence_runtime.py` ← `knowledge-graph`
  - `services/ai_agronomist/main.py` ← `KNOWLEDGE_GRAPH_URL`
  - `services/ai_agronomist/main.py` ← `knowledge-graph`
  - `services/mcp_servers/generic_context_server.py` ← `knowledge-graph`

### `supervisor-agent` — pass
classification: `ui`
- ui: 20 match(es)
  - `frontend/src/sections/ApprovalsConsolePage.tsx` ← `agent`
  - `frontend/src/sections/ChatbotPage.endpoint.test.ts` ← `/api/agent`
  - `frontend/src/sections/ChatbotPage.endpoint.test.ts` ← `agent`
  - `frontend/src/sections/MapHub.tsx` ← `agent`
  - `frontend/src/hooks/useApi.ts` ← `/api/agent`
- gateway: 8 match(es)
  - `nginx/nginx.unified.conf` ← `/api/agent/`
  - `nginx/nginx.unified.conf` ← `supervisor_backend`
  - `nginx/nginx.light.conf` ← `/api/agent/`
  - `nginx/nginx.light.conf` ← `supervisor_backend`
  - `nginx/nginx.fixed.conf` ← `/api/agent/`

### `guardrails-engine` — pass
classification: `ui`
- ui: 99 match(es)
  - `frontend/src/App.tsx` ← `approval`
  - `frontend/src/config/backendCoverageRegistry.ts` ← `approval`
  - `frontend/src/components/AddFieldWithMap.tsx` ← `validate`
  - `frontend/src/components/AddSeasonWithStages.tsx` ← `validate`
  - `frontend/src/components/AddFieldWithMap.undoredo.test.tsx` ← `validate`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf` ← `/api/guardrails/`
  - `nginx/nginx.fixed.conf` ← `guardrails_backend`
  - `nginx/nginx.v9.conf` ← `/api/guardrails/`
  - `nginx/nginx.v9.conf` ← `guardrails_backend`

### `agriai-engine` — pass
classification: `internal`
- internal-consumer: 11 match(es)
  - `docker-compose.unified.yml` ← `MCP_AGRIAI_URL`
  - `docker-compose.unified.yml` ← `agriai-engine`
  - `docker-compose.unified.yml` ← `sahool-unified-agriai-engine`
  - `tests_v9/smoke_services.py` ← `agriai-engine`
  - `tests_v9/test_simulation_capability_contract.py` ← `agriai-engine`

### `mcp_servers` — pass
classification: `internal`
- internal-consumer: 94 match(es)
  - `services/supervisor-agent/advisory_skill.py` ← `MCP`
  - `services/supervisor-agent/remote_sensing_skill.py` ← `MCP`
  - `services/supervisor-agent/remote_sensing_skill.py` ← `sentinel`
  - `services/supervisor-agent/mcp_client.py` ← `MCP`
  - `services/supervisor-agent/router.py` ← `sentinel`

### `actuator-service` — pass
classification: `ui`
- ui: 195 match(es)
  - `frontend/src/App.tsx` ← `irrigation`
  - `frontend/src/config/backendCoverageRegistry.ts` ← `irrigation`
  - `frontend/src/config/backendCoverageRegistry.ts` ← `schedule`
  - `frontend/src/components/AddFieldWithMap.tsx` ← `irrigation`
  - `frontend/src/components/AddSeasonWithStages.tsx` ← `irrigation`
- platform-proxy: 99 match(es)
  - `services/sahool-platform/core/dispatch_notification.py` ← `dispatch`
  - `services/sahool-platform/core/outcome_reconciler.py` ← `dispatch`
  - `services/sahool-platform/core/field_intelligence_coordinator.py` ← `dispatch`
  - `services/sahool-platform/core/execution_ledger_entry.py` ← `dispatch`
  - `services/sahool-platform/core/decision_dispatch.py` ← `actuator-service`

### `edge-inference` — pass
classification: `ui`
- ui: 126 match(es)
  - `frontend/src/App.tsx` ← `pest`
  - `frontend/src/App.tsx` ← `yield`
  - `frontend/src/config/backendCoverageRegistry.ts` ← `pest`
  - `frontend/src/components/AddSeasonWithStages.tsx` ← `yield`
  - `frontend/src/components/FieldDetailPanel.tsx` ← `yield`
- platform-proxy: 3 match(es)
  - `services/sahool-platform/core/capabilities.py` ← `edge-inference`
  - `services/sahool-platform/api/routers/service_proxy.py` ← `EDGE_INFERENCE_URL`
  - `services/sahool-platform/api/routers/service_proxy.py` ← `edge-inference`

### `video-processor` — pass
classification: `ui`
- ui: 30 match(es)
  - `frontend/src/App.tsx` ← `DevicesPage`
  - `frontend/src/components/maphub/weather/weatherLayerDefinitions.ts` ← `stream`
  - `frontend/src/components/approvals/DecisionEvidencePanel.tsx` ← `snapshot`
  - `frontend/src/components/fieldview/DistrictsWeatherCard.tsx` ← `stream`
  - `frontend/src/components/fieldview/EvidenceHistoryCard.tsx` ← `snapshot`
- platform-proxy: 4 match(es)
  - `services/sahool-platform/api/field_cameras.py` ← `field_cameras`
  - `services/sahool-platform/api/field_cameras.py` ← `video-processor`
  - `services/sahool-platform/api/device_registry.py` ← `field_cameras`
  - `services/sahool-platform/api/routers/cameras.py` ← `field_cameras`

### `weather-polygon-worker` — pass
classification: `ui-indirect`
- ui: 7 match(es)
  - `frontend/src/components/maphub/weather/README.md` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts` ← `operation-tile-data`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts` ← `tile-data`
  - `frontend/src/components/maphub/weather/WeatherTileLayer.ts` ← `operation-tile-data`
- internal-consumer: 11 match(es)
  - `services/sahool-platform/core/weather_overlay_pipeline.py` ← `field_weather_overlay`
  - `services/sahool-platform/core/weather_overlay_pipeline.py` ← `weather_overlay_pipeline`
  - `services/sahool-platform/core/weather_overlay_pipeline.py` ← `weather-polygon-worker`
  - `services/sahool-platform/tests/test_weather_overlay_pipeline.py` ← `weather_overlay_pipeline`
  - `services/sahool-platform/tests/test_weather_overlay_pipeline.py` ← `weather-polygon-worker`

### `weather-signal-engine` — pass
classification: `internal`
- internal-consumer: 17 match(es)
  - `services/sahool-platform/core/weather_overlay_pipeline.py` ← `weather_signals`
  - `services/sahool-platform/core/decision_playbook.py` ← `weather_signals`
  - `services/sahool-platform/core/decision_playbook.py` ← `decision_playbook`
  - `services/sahool-platform/core/weather_signals.py` ← `weather_signals`
  - `services/sahool-platform/api/field_season_projection.py` ← `weather_signals`

### `erp-bridge` — pass
classification: `integration`
- gateway-or-internal: 13 match(es)
  - `nginx/nginx.unified.conf` ← `/api/erp/`
  - `nginx/nginx.unified.conf` ← `erp-bridge`
  - `services/mcp_servers/market_server.py` ← `ERP_BRIDGE_URL`
  - `services/mcp_servers/market_server.py` ← `erp-bridge`
  - `docker-compose.v9.yml` ← `ERP_BRIDGE_URL`

### `tts-service` — pass
classification: `ui`
- ui: 8 match(es)
  - `frontend/src/components/SpeakButton.tsx` ← `SpeakButton`
  - `frontend/src/components/SpeakButton.tsx` ← `synthesize`
  - `frontend/src/components/SpeakButton.tsx` ← `tts`
  - `frontend/src/sections/RecommendationPage.tsx` ← `SpeakButton`
  - `frontend/src/sections/maphub/FieldTimelineShell.tsx` ← `synthesize`

### `local-ai-rag` — pass
classification: `internal`
- internal-consumer: 64 match(es)
  - `services/supervisor-agent/advisory_skill.py` ← `RAG`
  - `services/supervisor-agent/test_ai_orchestration_forensic.py` ← `LOCAL_AI_RAG_URL`
  - `services/supervisor-agent/test_ai_orchestration_forensic.py` ← `RAG`
  - `services/supervisor-agent/skills/advisory_skill.py` ← `LOCAL_AI_RAG_URL`
  - `services/supervisor-agent/skills/advisory_skill.py` ← `local-ai-rag`

### `raster-tiler-service` — pass
classification: `internal`
- internal-consumer: 70 match(es)
  - `services/raster-service/test_db_rehydrate.py` ← `tilejson`
  - `services/raster-service/test_cloud_native_catalog.py` ← `tilejson`
  - `services/raster-service/raster_main_compat_exports.py` ← `TITILER_URL`
  - `services/raster-service/raster_main_compat_exports.py` ← `tilejson`
  - `services/raster-service/test_tile_tenant_query.py` ← `tilejson`

### `qdrant-seed` — pass
classification: `job`
- job-contract: 18 match(es)
  - `docker-compose.v9.yml` ← `qdrant-seed`
  - `docker-compose.v9.yml` ← `QDRANT`
  - `docker-compose.fixed.yml` ← `qdrant-seed`
  - `docker-compose.fixed.yml` ← `QDRANT`
  - `docker-compose.rag-kg-mcp.yml` ← `QDRANT`

### `decision-service` — pass
classification: `internal-sensitive`
- internal-consumer: 25 match(es)
  - `services/sahool-platform/api/lexicographic_mpc_bridge.py` ← `decision_service_client`
  - `services/sahool-platform/api/irrigation_dispatch_relay_worker.py` ← `decision_service_client`
  - `services/sahool-platform/api/water_decision_bridge.py` ← `decision_service_client`
  - `services/sahool-platform/api/phase_runtime_store.py` ← `decision_service_client`
  - `services/sahool-platform/api/irrigation_activation_gate.py` ← `DECISION_SERVICE_URL`

### `model-registry-adapter` — pass
classification: `internal`
- internal-consumer: 6 match(es)
  - `services/model-registry-adapter/worker.py` ← `DECISION_SERVICE_URL`
  - `services/model-registry-adapter/runtime.py` ← `DECISION_SERVICE_URL`
  - `services/model-registry-adapter/tests/test_runtime_contract.py` ← `DECISION_SERVICE_URL`
  - `docker-compose.v9.yml` ← `DECISION_SERVICE_URL`
  - `docker-compose.v9.yml` ← `sahool-model-registry-worker`

### `gis-workflow-service` — pass
classification: `internal`
- internal-consumer: 20 match(es)
  - `services/gis-workflow-service/README.md` ← `publication_map`
  - `services/gis-workflow-service/README.md` ← `bulletin`
  - `services/gis-workflow-service/README.md` ← `map_layout`
  - `services/gis-workflow-service/publication_map.py` ← `publication_map`
  - `services/gis-workflow-service/publication_map.py` ← `map_layout`

### `remote-sensing-workspace-bff` — pass
classification: `internal`
- internal-consumer: 4 match(es)
  - `docker-compose.v9.yml` ← `remote-sensing-workspace-bff`
  - `docker-compose.v9.yml` ← `WORKSPACE_BFF_TIMEOUT_S`
  - `docker-compose.v9.yml` ← `remote-sensing-workspace`
  - `services/remote-sensing-workspace-bff/tests/test_workspace_bff.py` ← `remote-sensing-workspace`

### `field-management-service` — pass
classification: `internal-sensitive`
- internal-consumer: 6 match(es)
  - `services/vegetation-analysis-service/vegetation_runtime.py` ← `FIELD_SERVICE_URL`
  - `services/vegetation-analysis-service/vegetation_runtime.py` ← `/internal/fields`
  - `services/vegetation-analysis-service/test_platform_field_catalog_boundary.py` ← `FIELD_SERVICE_URL`
  - `services/vegetation-analysis-service/test_platform_field_catalog_boundary.py` ← `/internal/fields`
  - `docker-compose.v9.yml` ← `FIELD_SERVICE_URL`

### `scout-ingest-service` — pass
classification: `internal-sensitive`
- internal-consumer: 7 match(es)
  - `services/scout-ingest-service/main.py` ← `/internal/ingest/submissions/odk`
  - `services/scout-ingest-service/main.py` ← `scout-ingest-service`
  - `services/scout-ingest-service/tests/test_ingest_live.py` ← `scout-ingest-service`
  - `docker-compose.v9.yml` ← `sahool-scout-ingest`
  - `docker-compose.v9.yml` ← `scout-ingest-service`
