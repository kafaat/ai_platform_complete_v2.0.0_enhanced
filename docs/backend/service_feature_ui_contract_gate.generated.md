# service-feature-ui-contract-gate report

- services: 26
- passed: 26
- failed: 0

## Service evidence

### `auth` — pass
classification: `ui`
- ui: 43 match(es)
  - `frontend/src/App.tsx` ← `LoginPage`
  - `frontend/src/App.tsx` ← `SignupPage`
  - `frontend/src/components/maphub/ImageryAutoRefreshGuard.static.test.ts` ← `refresh`
  - `frontend/src/hooks/useManagerConsole.ts` ← `/auth/`
  - `frontend/src/hooks/useApi.ts` ← `refresh`
- gateway: 8 match(es)
  - `nginx/nginx.light.conf` ← `/auth/`
  - `nginx/nginx.light.conf` ← `auth_backend`
  - `nginx/nginx.v9.conf` ← `/auth/`
  - `nginx/nginx.v9.conf` ← `auth_backend`
  - `nginx/nginx.fixed.conf` ← `/auth/`

### `sahool-platform` — pass
classification: `ui`
- ui: 190 match(es)
  - `frontend/src/components/FieldIndicatorMap.tsx` ← `AddFieldWithMap`
  - `frontend/src/components/AddFieldWithMap.undoredo.test.tsx` ← `AddFieldWithMap`
  - `frontend/src/components/AddFieldWithMap.workspace.test.tsx` ← `AddFieldWithMap`
  - `frontend/src/components/AddFieldWithMap.tsx` ← `/api/v1`
  - `frontend/src/components/AddFieldWithMap.tsx` ← `AddFieldWithMap`
- gateway: 4 match(es)
  - `nginx/nginx.v9.conf` ← `/api/v1/`
  - `nginx/nginx.v9.conf` ← `platform_backend`
  - `nginx/nginx.fixed.conf` ← `/api/v1/`
  - `nginx/nginx.fixed.conf` ← `platform_backend`

### `raster-service` — pass
classification: `ui`
- ui: 24 match(es)
  - `frontend/src/components/FieldIndicatorMap.tsx` ← `cdse-tilejson`
  - `frontend/src/components/FieldIndicatorMap.tsx` ← `tilejson`
  - `frontend/src/components/FieldIndicatorMap.tsx` ← `FieldIndicatorMap`
  - `frontend/src/components/FieldIndicatorMap.static.test.ts` ← `FieldIndicatorMap`
  - `frontend/src/components/maphub/MapHubTerrainSoilLayers.static.test.ts` ← `tilejson`
- gateway: 4 match(es)
  - `nginx/nginx.v9.conf` ← `/api/raster/`
  - `nginx/nginx.v9.conf` ← `raster_backend`
  - `nginx/nginx.fixed.conf` ← `/api/raster/`
  - `nginx/nginx.fixed.conf` ← `raster_backend`

### `vegetation-analysis-service` — pass
classification: `ui`
- ui: 96 match(es)
  - `frontend/src/App.tsx` ← `FieldRanking`
  - `frontend/src/components/NDVIGauge.tsx` ← `NDVI`
  - `frontend/src/components/sql/SQLEditor.tsx` ← `NDVI`
  - `frontend/src/components/maphub/DataFreshnessBadge.tsx` ← `NDVI`
  - `frontend/src/components/maphub/DataFreshnessBadge.test.tsx` ← `NDVI`
- gateway: 4 match(es)
  - `nginx/nginx.v9.conf` ← `/api/vegetation/`
  - `nginx/nginx.v9.conf` ← `vegetation_backend`
  - `nginx/nginx.fixed.conf` ← `/api/vegetation/`
  - `nginx/nginx.fixed.conf` ← `vegetation_backend`

### `indicators-service` — pass
classification: `ui`
- ui: 29 match(es)
  - `frontend/src/App.tsx` ← `HybridIndexPage`
  - `frontend/src/App.tsx` ← `indicators`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts` ← `indicators`
  - `frontend/src/components/insights/MapIndicatorLegend.test.tsx` ← `indicators`
  - `frontend/src/config/endpoints.ts` ← `indicators`
- gateway: 4 match(es)
  - `nginx/nginx.v9.conf` ← `/api/indicators/`
  - `nginx/nginx.v9.conf` ← `indicators_backend`
  - `nginx/nginx.fixed.conf` ← `/api/indicators/`
  - `nginx/nginx.fixed.conf` ← `indicators_backend`

### `weather-service` — pass
classification: `ui`
- ui: 15 match(es)
  - `frontend/src/App.tsx` ← `WeatherAdvice`
  - `frontend/src/components/maphub/weather/WeatherRasterOverlay.tsx` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/WeatherRasterOverlay.tsx` ← `WeatherProbePopup`
  - `frontend/src/components/maphub/weather/WeatherHoverReadout.ts` ← `WeatherProbePopup`
  - `frontend/src/components/maphub/weather/README.md` ← `WeatherTileLayer`
- platform-proxy: 284 match(es)
  - `services/sahool-platform/api/season_simulation.py` ← `weather-service`
  - `services/sahool-platform/api/season_simulation.py` ← `weather`
  - `services/sahool-platform/api/main.py` ← `weather`
  - `services/sahool-platform/api/event_replay.py` ← `weather`
  - `services/sahool-platform/api/season_models.py` ← `weather`

### `soil-service` — pass
classification: `ui`
- ui: 142 match(es)
  - `frontend/src/App.tsx` ← `soil`
  - `frontend/src/components/AddFieldWithMap.tsx` ← `soil`
  - `frontend/src/components/AddFieldWithMap.tsx` ← `Soil`
  - `frontend/src/components/FieldDetailPanel.tsx` ← `soil`
  - `frontend/src/components/maphub/ProductivityZonesPanel.tsx` ← `soil`
- platform-proxy: 262 match(es)
  - `services/sahool-platform/README.md` ← `soil`
  - `services/sahool-platform/api/main.py` ← `soil`
  - `services/sahool-platform/api/event_replay.py` ← `soil`
  - `services/sahool-platform/api/data_quality.py` ← `soil`
  - `services/sahool-platform/api/prescriptions.py` ← `soil`

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
  - `services/field-segmentation/main.py` ← `SEGMENTATION_INFERENCE_URL`
  - `services/field-segmentation/main.py` ← `SEGMENTATION_BACKEND`
  - `services/field-segmentation/main.py` ← `sam2`
  - `services/field-segmentation/test_segmentation.py` ← `SEGMENTATION_INFERENCE_URL`
  - `services/field-segmentation/test_segmentation.py` ← `SEGMENTATION_BACKEND`

### `ai_agronomist` — pass
classification: `ui`
- ui: 18 match(es)
  - `frontend/src/App.tsx` ← `ChatbotPage`
  - `frontend/src/hooks/useApi.ts` ← `ai-agronomist`
  - `frontend/src/hooks/fieldViewUiWide.static.test.ts` ← `ChatbotPage`
  - `frontend/src/sections/ChatbotApprovalUi.v58.static.test.ts` ← `ChatbotPage`
  - `frontend/src/sections/ChatbotApprovalUi.v58.static.test.ts` ← `ai-agronomist`
- gateway: 2 match(es)
  - `nginx/nginx.v9.conf` ← `/api/ai-agronomist/`
  - `nginx/nginx.v9.conf` ← `ai_agronomist_backend`

### `rag-retrieval` — pass
classification: `internal-sensitive`
- internal-consumer: 16 match(es)
  - `services/ai_agronomist/main.py` ← `RAG_BASE_URL`
  - `services/ai_agronomist/main.py` ← `rag-retrieval`
  - `services/ai_agronomist/ai_evidence_runtime.py` ← `RAG_BASE_URL`
  - `services/ai_agronomist/ai_evidence_runtime.py` ← `rag-retrieval`
  - `tests_v9/test_real_findings_closure_20260702.py` ← `rag-retrieval`

### `knowledge-graph` — pass
classification: `internal-sensitive`
- internal-consumer: 20 match(es)
  - `services/ai_agronomist/main.py` ← `KNOWLEDGE_GRAPH_URL`
  - `services/ai_agronomist/main.py` ← `knowledge-graph`
  - `services/ai_agronomist/ai_evidence_runtime.py` ← `KNOWLEDGE_GRAPH_URL`
  - `services/ai_agronomist/ai_evidence_runtime.py` ← `knowledge-graph`
  - `services/mcp_servers/generic_context_server.py` ← `knowledge-graph`

### `supervisor-agent` — pass
classification: `ui`
- ui: 20 match(es)
  - `frontend/src/hooks/useApi.ts` ← `/api/agent`
  - `frontend/src/hooks/useApi.ts` ← `supervisor`
  - `frontend/src/hooks/useApi.ts` ← `agent`
  - `frontend/src/services/api/client.ts` ← `/api/agent`
  - `frontend/src/services/api/client.ts` ← `agent`
- gateway: 8 match(es)
  - `nginx/nginx.light.conf` ← `/api/agent/`
  - `nginx/nginx.light.conf` ← `supervisor_backend`
  - `nginx/nginx.v9.conf` ← `/api/agent/`
  - `nginx/nginx.v9.conf` ← `supervisor_backend`
  - `nginx/nginx.fixed.conf` ← `/api/agent/`

### `guardrails-engine` — pass
classification: `ui`
- ui: 85 match(es)
  - `frontend/src/App.tsx` ← `approval`
  - `frontend/src/components/AddFieldWithMap.undoredo.test.tsx` ← `validate`
  - `frontend/src/components/AddFieldWithMap.workspace.test.tsx` ← `validate`
  - `frontend/src/components/AddFieldWithMap.tsx` ← `validate`
  - `frontend/src/components/AddSeasonWithStages.tsx` ← `validate`
- gateway: 4 match(es)
  - `nginx/nginx.v9.conf` ← `/api/guardrails/`
  - `nginx/nginx.v9.conf` ← `guardrails_backend`
  - `nginx/nginx.fixed.conf` ← `/api/guardrails/`
  - `nginx/nginx.fixed.conf` ← `guardrails_backend`

### `agriai-engine` — pass
classification: `internal`
- internal-consumer: 8 match(es)
  - `docker-compose.unified.yml` ← `MCP_AGRIAI_URL`
  - `docker-compose.unified.yml` ← `agriai-engine`
  - `docker-compose.unified.yml` ← `sahool-unified-agriai-engine`
  - `tests_v9/test_crop_model_uncertainty_v64.py` ← `agriai-engine`
  - `tests_v9/test_real_findings_closure_20260702.py` ← `agriai-engine`

### `mcp_servers` — pass
classification: `internal`
- internal-consumer: 93 match(es)
  - `services/supervisor-agent/test_graceful_degradation.py` ← `MCP`
  - `services/supervisor-agent/main.py` ← `MCP`
  - `services/supervisor-agent/main.py` ← `sentinel`
  - `services/supervisor-agent/test_chaos_resilience.py` ← `sentinel`
  - `services/supervisor-agent/market_skill.py` ← `MCP`

### `actuator-service` — pass
classification: `ui`
- ui: 174 match(es)
  - `frontend/src/App.tsx` ← `irrigation`
  - `frontend/src/components/AddFieldWithMap.tsx` ← `irrigation`
  - `frontend/src/components/FieldDetailPanel.tsx` ← `irrigation`
  - `frontend/src/components/AddSeasonWithStages.tsx` ← `irrigation`
  - `frontend/src/components/maphub/FieldDetailDrawer.tsx` ← `irrigation`
- platform-proxy: 81 match(es)
  - `services/sahool-platform/api/phase_runtime_store.py` ← `dispatch`
  - `services/sahool-platform/api/phase_runtime_workers.py` ← `dispatch`
  - `services/sahool-platform/api/command_store.py` ← `dispatch`
  - `services/sahool-platform/api/decision_service_client.py` ← `dispatch`
  - `services/sahool-platform/api/command_dispatcher.py` ← `dispatch`

### `edge-inference` — pass
classification: `ui`
- ui: 120 match(es)
  - `frontend/src/App.tsx` ← `pest`
  - `frontend/src/App.tsx` ← `yield`
  - `frontend/src/components/FieldDetailPanel.tsx` ← `yield`
  - `frontend/src/components/AddSeasonWithStages.tsx` ← `yield`
  - `frontend/src/components/maphub/FieldDetailDrawer.tsx` ← `yield`
- platform-proxy: 3 match(es)
  - `services/sahool-platform/api/routers/service_proxy.py` ← `EDGE_INFERENCE_URL`
  - `services/sahool-platform/api/routers/service_proxy.py` ← `edge-inference`
  - `services/sahool-platform/core/capabilities.py` ← `edge-inference`

### `video-processor` — pass
classification: `ui`
- ui: 23 match(es)
  - `frontend/src/App.tsx` ← `DevicesPage`
  - `frontend/src/components/maphub/weather/weatherLayerDefinitions.ts` ← `stream`
  - `frontend/src/components/fieldview/WaterFieldOpsCard.tsx` ← `stream`
  - `frontend/src/components/fieldview/EvidenceHistoryCard.tsx` ← `snapshot`
  - `frontend/src/components/fieldview/DistrictsWeatherCard.tsx` ← `stream`
- platform-proxy: 4 match(es)
  - `services/sahool-platform/api/device_registry.py` ← `field_cameras`
  - `services/sahool-platform/api/field_cameras.py` ← `field_cameras`
  - `services/sahool-platform/api/field_cameras.py` ← `video-processor`
  - `services/sahool-platform/api/routers/cameras.py` ← `field_cameras`

### `weather-polygon-worker` — pass
classification: `ui-indirect`
- ui: 7 match(es)
  - `frontend/src/components/maphub/weather/WeatherRasterOverlay.tsx` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/README.md` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts` ← `operation-tile-data`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts` ← `tile-data`
- internal-consumer: 10 match(es)
  - `services/sahool-platform/tests/test_weather_overlay_pipeline.py` ← `weather_overlay_pipeline`
  - `services/sahool-platform/tests/test_weather_overlay_pipeline.py` ← `weather-polygon-worker`
  - `services/sahool-platform/core/weather_overlay_pipeline.py` ← `field_weather_overlay`
  - `services/sahool-platform/core/weather_overlay_pipeline.py` ← `weather_overlay_pipeline`
  - `services/sahool-platform/core/weather_overlay_pipeline.py` ← `weather-polygon-worker`

### `weather-signal-engine` — pass
classification: `internal`
- internal-consumer: 17 match(es)
  - `services/sahool-platform/api/field_season_projection.py` ← `weather_signals`
  - `services/sahool-platform/api/routers/agro_intelligence.py` ← `weather_signals`
  - `services/sahool-platform/api/routers/agro_intelligence.py` ← `decision_playbook`
  - `services/sahool-platform/tests/test_field_season_projection.py` ← `weather_signals`
  - `services/sahool-platform/tests/test_agro_intelligence_endpoints.py` ← `weather_signals`

### `erp-bridge` — pass
classification: `integration`
- gateway-or-internal: 12 match(es)
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
  - `frontend/src/services/api.ts` ← `synthesize`
  - `frontend/src/services/api.ts` ← `tts`

### `local-ai-rag` — pass
classification: `internal`
- internal-consumer: 61 match(es)
  - `services/supervisor-agent/test_ai_orchestration_forensic.py` ← `LOCAL_AI_RAG_URL`
  - `services/supervisor-agent/test_ai_orchestration_forensic.py` ← `RAG`
  - `services/supervisor-agent/advisory_skill.py` ← `RAG`
  - `services/supervisor-agent/skills/advisory_skill.py` ← `LOCAL_AI_RAG_URL`
  - `services/supervisor-agent/skills/advisory_skill.py` ← `local-ai-rag`

### `raster-tiler-service` — pass
classification: `internal`
- internal-consumer: 67 match(es)
  - `services/raster-service/test_router_query_direct_call.py` ← `tilejson`
  - `services/raster-service/main.py` ← `TITILER_URL`
  - `services/raster-service/raster_job_orchestration.py` ← `tilejson`
  - `services/raster-service/test_tiles.py` ← `tilejson`
  - `services/raster-service/test_raster_map_deep_hardening_static.py` ← `tilejson`

### `qdrant-seed` — pass
classification: `job`
- job-contract: 18 match(es)
  - `docker-compose.v9.yml` ← `qdrant-seed`
  - `docker-compose.v9.yml` ← `QDRANT`
  - `docker-compose.fixed.yml` ← `qdrant-seed`
  - `docker-compose.fixed.yml` ← `QDRANT`
  - `docker-compose.rag-kg-mcp.yml` ← `QDRANT`
