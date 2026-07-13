# service-feature-ui-contract-gate report

- services: 26
- passed: 26
- failed: 0

## Service evidence

### `auth` — pass
classification: `ui`
- ui: 44 match(es)
  - `frontend/src/App.tsx` ← `LoginPage`
  - `frontend/src/App.tsx` ← `SignupPage`
  - `frontend/src/components/maphub/ImageryAutoRefreshGuard.static.test.ts` ← `refresh`
  - `frontend/src/sections/MapHubTwoYearBackfill.static.test.ts` ← `refresh`
  - `frontend/src/sections/MapHub.tsx` ← `refresh`
- gateway: 8 match(es)
  - `nginx/nginx.unified.conf` ← `/auth/`
  - `nginx/nginx.unified.conf` ← `auth_backend`
  - `nginx/nginx.v9.conf` ← `/auth/`
  - `nginx/nginx.v9.conf` ← `auth_backend`
  - `nginx/nginx.light.conf` ← `/auth/`

### `sahool-platform` — pass
classification: `ui`
- ui: 192 match(es)
  - `frontend/src/lib/agronomyConsistency.ts` ← `/api/v1`
  - `frontend/src/lib/fieldProfitability.ts` ← `/api/v1`
  - `frontend/src/lib/waterHarvesting.ts` ← `/api/v1`
  - `frontend/src/lib/mapRegression.test.ts` ← `AddFieldWithMap`
  - `frontend/src/lib/recommendationsLifecycle.ts` ← `/api/v1`
- gateway: 4 match(es)
  - `nginx/nginx.v9.conf` ← `/api/v1/`
  - `nginx/nginx.v9.conf` ← `platform_backend`
  - `nginx/nginx.fixed.conf` ← `/api/v1/`
  - `nginx/nginx.fixed.conf` ← `platform_backend`

### `raster-service` — pass
classification: `ui`
- ui: 24 match(es)
  - `frontend/src/lib/geo.ts` ← `FieldIndicatorMap`
  - `frontend/src/lib/layerRegistry.ts` ← `FieldIndicatorMap`
  - `frontend/src/lib/leafletSetup.ts` ← `FieldIndicatorMap`
  - `frontend/src/components/FieldIndicatorMap.static.test.ts` ← `FieldIndicatorMap`
  - `frontend/src/components/FieldIndicatorMap.tsx` ← `cdse-tilejson`
- gateway: 4 match(es)
  - `nginx/nginx.v9.conf` ← `/api/raster/`
  - `nginx/nginx.v9.conf` ← `raster_backend`
  - `nginx/nginx.fixed.conf` ← `/api/raster/`
  - `nginx/nginx.fixed.conf` ← `raster_backend`

### `vegetation-analysis-service` — pass
classification: `ui`
- ui: 98 match(es)
  - `frontend/src/App.tsx` ← `FieldRanking`
  - `frontend/src/lib/fieldObjectiveEngine.ts` ← `NDVI`
  - `frontend/src/lib/layerRegistry.test.ts` ← `NDVI`
  - `frontend/src/lib/realData.test.ts` ← `FieldRanking`
  - `frontend/src/lib/gisWorkbench.test.ts` ← `NDVI`
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
  - `frontend/src/lib/permissions.ts` ← `indicators`
  - `frontend/src/lib/fieldOperatingContract.ts` ← `indicators`
  - `frontend/src/lib/learningEvidence.ts` ← `indicators`
- gateway: 4 match(es)
  - `nginx/nginx.v9.conf` ← `/api/indicators/`
  - `nginx/nginx.v9.conf` ← `indicators_backend`
  - `nginx/nginx.fixed.conf` ← `/api/indicators/`
  - `nginx/nginx.fixed.conf` ← `indicators_backend`

### `weather-service` — pass
classification: `ui`
- ui: 15 match(es)
  - `frontend/src/App.tsx` ← `WeatherAdvice`
  - `frontend/src/components/maphub/weather/README.md` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/README.md` ← `WeatherProbePopup`
  - `frontend/src/components/maphub/weather/WeatherProbePopup.ts` ← `WeatherProbePopup`
  - `frontend/src/components/maphub/weather/WeatherProbePopup.ts` ← `operation-window`
- platform-proxy: 288 match(es)
  - `services/sahool-platform/core/api_adapter.py` ← `weather`
  - `services/sahool-platform/core/guardrails.py` ← `weather`
  - `services/sahool-platform/core/canonical_field_state_lock.py` ← `weather`
  - `services/sahool-platform/core/weather_overlay_pipeline.py` ← `weather`
  - `services/sahool-platform/core/agronomic_decision.py` ← `weather`

### `soil-service` — pass
classification: `ui`
- ui: 152 match(es)
  - `frontend/src/App.tsx` ← `soil`
  - `frontend/src/lib/featureFlags.ts` ← `soil`
  - `frontend/src/lib/specialtyCrops.test.ts` ← `soil`
  - `frontend/src/lib/fieldWaterBrain.test.ts` ← `soil`
  - `frontend/src/lib/decisionDeep.ts` ← `soil`
- platform-proxy: 269 match(es)
  - `services/sahool-platform/README.md` ← `soil`
  - `services/sahool-platform/core/sensor_intake.py` ← `soil`
  - `services/sahool-platform/core/guardrails.py` ← `soil`
  - `services/sahool-platform/core/agronomic_decision.py` ← `soil`
  - `services/sahool-platform/core/agronomic_state_engine.py` ← `soil`

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
  - `services/field-segmentation/main.py` ← `SEGMENTATION_INFERENCE_URL`
  - `services/field-segmentation/main.py` ← `SEGMENTATION_BACKEND`
  - `services/field-segmentation/main.py` ← `sam2`
  - `services/field-segmentation/test_segmentation.py` ← `SEGMENTATION_INFERENCE_URL`

### `ai_agronomist` — pass
classification: `ui`
- ui: 18 match(es)
  - `frontend/src/App.tsx` ← `ChatbotPage`
  - `frontend/src/lib/approvalsConsole.test.ts` ← `ChatbotPage`
  - `frontend/src/sections/ChatbotPage.tsx` ← `ChatbotPage`
  - `frontend/src/sections/ChatbotPage.tsx` ← `ai-agronomist`
  - `frontend/src/sections/ChatbotProviderToolApproval.v58.static.test.ts` ← `ChatbotPage`
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
  - `tests_v9/test_gateway_trusted_identity_sec3.py` ← `rag-retrieval`

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
  - `frontend/src/lib/fieldViewDecisionScript.test.ts` ← `agent`
  - `frontend/src/lib/fieldOperatingContract.ts` ← `supervisor`
  - `frontend/src/lib/fieldViewGovernance.test.ts` ← `agent`
  - `frontend/src/lib/designSystemGovernance.ts` ← `agent`
  - `frontend/src/lib/fieldViewActionDeck.ts` ← `agent`
- gateway: 8 match(es)
  - `nginx/nginx.unified.conf` ← `/api/agent/`
  - `nginx/nginx.unified.conf` ← `supervisor_backend`
  - `nginx/nginx.v9.conf` ← `/api/agent/`
  - `nginx/nginx.v9.conf` ← `supervisor_backend`
  - `nginx/nginx.light.conf` ← `/api/agent/`

### `guardrails-engine` — pass
classification: `ui`
- ui: 92 match(es)
  - `frontend/src/App.tsx` ← `approval`
  - `frontend/src/lib/agronomyConsistency.ts` ← `approval`
  - `frontend/src/lib/agronomyConsistency.ts` ← `validate`
  - `frontend/src/lib/recommendationsLifecycle.ts` ← `validate`
  - `frontend/src/lib/decisionDeep.ts` ← `approval`
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
  - `tests_v9/test_v9_feature_transfer_20260702.py` ← `agriai-engine`
  - `tests_v9/test_agriai_engine_features_20260702.py` ← `agriai-engine`

### `mcp_servers` — pass
classification: `internal`
- internal-consumer: 93 match(es)
  - `services/supervisor-agent/test_ai_orchestration_forensic.py` ← `MCP`
  - `services/supervisor-agent/test_ai_orchestration_forensic.py` ← `sentinel`
  - `services/supervisor-agent/market_skill.py` ← `MCP`
  - `services/supervisor-agent/test_graceful_degradation.py` ← `MCP`
  - `services/supervisor-agent/advisory_skill.py` ← `MCP`

### `actuator-service` — pass
classification: `ui`
- ui: 177 match(es)
  - `frontend/src/App.tsx` ← `irrigation`
  - `frontend/src/lib/featureFlags.ts` ← `irrigation`
  - `frontend/src/lib/agronomyConsistency.test.ts` ← `irrigation`
  - `frontend/src/lib/fieldObjectiveHiddenGaps.test.ts` ← `schedule`
  - `frontend/src/lib/fieldObjectiveEngine.ts` ← `irrigation`
- platform-proxy: 84 match(es)
  - `services/sahool-platform/core/loop_referential_integrity.py` ← `dispatch`
  - `services/sahool-platform/core/outcome_reconciler.py` ← `dispatch`
  - `services/sahool-platform/core/agronomic_decision.py` ← `dispatch`
  - `services/sahool-platform/core/impact_measurement.py` ← `dispatch`
  - `services/sahool-platform/core/policy_registry.py` ← `dispatch`

### `edge-inference` — pass
classification: `ui`
- ui: 121 match(es)
  - `frontend/src/App.tsx` ← `pest`
  - `frontend/src/App.tsx` ← `yield`
  - `frontend/src/lib/fieldProfitability.ts` ← `yield`
  - `frontend/src/lib/ledgerEntry.ts` ← `pest`
  - `frontend/src/lib/fieldScouting.test.ts` ← `pest`
- platform-proxy: 3 match(es)
  - `services/sahool-platform/core/capabilities.py` ← `edge-inference`
  - `services/sahool-platform/api/routers/service_proxy.py` ← `EDGE_INFERENCE_URL`
  - `services/sahool-platform/api/routers/service_proxy.py` ← `edge-inference`

### `video-processor` — pass
classification: `ui`
- ui: 29 match(es)
  - `frontend/src/App.tsx` ← `DevicesPage`
  - `frontend/src/lib/evidenceHistory.test.ts` ← `snapshot`
  - `frontend/src/lib/evidenceHistory.ts` ← `snapshot`
  - `frontend/src/lib/precisionAgriculture.ts` ← `snapshot`
  - `frontend/src/lib/districtsWeather.ts` ← `stream`
- platform-proxy: 4 match(es)
  - `services/sahool-platform/api/device_registry.py` ← `field_cameras`
  - `services/sahool-platform/api/field_cameras.py` ← `field_cameras`
  - `services/sahool-platform/api/field_cameras.py` ← `video-processor`
  - `services/sahool-platform/api/routers/cameras.py` ← `field_cameras`

### `weather-polygon-worker` — pass
classification: `ui-indirect`
- ui: 7 match(es)
  - `frontend/src/components/maphub/weather/README.md` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts` ← `operation-tile-data`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts` ← `tile-data`
  - `frontend/src/components/maphub/weather/WeatherTileLayer.ts` ← `operation-tile-data`
- internal-consumer: 10 match(es)
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
- gateway-or-internal: 12 match(es)
  - `nginx/nginx.unified.conf` ← `/api/erp/`
  - `nginx/nginx.unified.conf` ← `erp-bridge`
  - `services/mcp_servers/market_server.py` ← `ERP_BRIDGE_URL`
  - `services/mcp_servers/market_server.py` ← `erp-bridge`
  - `docker-compose.v9.yml` ← `ERP_BRIDGE_URL`

### `tts-service` — pass
classification: `ui`
- ui: 8 match(es)
  - `frontend/src/lib/fieldObjectiveHiddenGaps.test.ts` ← `synthesize`
  - `frontend/src/components/SpeakButton.tsx` ← `SpeakButton`
  - `frontend/src/components/SpeakButton.tsx` ← `synthesize`
  - `frontend/src/components/SpeakButton.tsx` ← `tts`
  - `frontend/src/sections/RecommendationPage.tsx` ← `SpeakButton`

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
  - `services/raster-service/cloud_native_catalog.py` ← `tilejson`
  - `services/raster-service/raster_cdse_tile_runtime.py` ← `tilejson`
  - `services/raster-service/test_router_query_direct_call.py` ← `tilejson`
  - `services/raster-service/test_raster_map_deep_hardening_static.py` ← `tilejson`
  - `services/raster-service/raster_pixel_processing.py` ← `tilejson`

### `qdrant-seed` — pass
classification: `job`
- job-contract: 18 match(es)
  - `docker-compose.v9.yml` ← `qdrant-seed`
  - `docker-compose.v9.yml` ← `QDRANT`
  - `docker-compose.fixed.yml` ← `qdrant-seed`
  - `docker-compose.fixed.yml` ← `QDRANT`
  - `docker-compose.rag-kg-mcp.yml` ← `QDRANT`
