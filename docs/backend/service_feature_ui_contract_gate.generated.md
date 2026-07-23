# service-feature-ui-contract-gate report

- services: 32
- passed: 32
- failed: 0

## Service evidence

### `auth` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 51 match(es)
  - `frontend/src/App.tsx:53` ← `LoginPage`
  - `frontend/src/App.tsx:54` ← `SignupPage`
  - `frontend/src/components/fieldview/NdviUnavailableNotice.tsx:21` ← `refresh`
  - `frontend/src/components/maphub/ImageryAutoRefreshGuard.static.test.ts:8` ← `refresh`
  - `frontend/src/hooks/TenantCacheIsolation.static.test.ts:40` ← `refresh`
- gateway: 8 match(es)
  - `nginx/nginx.fixed.conf:51` ← `/auth/`
  - `nginx/nginx.fixed.conf:20` ← `auth_backend`
  - `nginx/nginx.light.conf:69` ← `/auth/`
  - `nginx/nginx.light.conf:33` ← `auth_backend`
  - `nginx/nginx.unified.conf:78` ← `/auth/`

### `sahool-platform` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 206 match(es)
  - `frontend/src/components/AddFieldWithMap.tsx:430` ← `/api/v1`
  - `frontend/src/components/AddFieldWithMap.tsx:2` ← `AddFieldWithMap`
  - `frontend/src/components/AddFieldWithMap.undoredo.test.tsx:6` ← `AddFieldWithMap`
  - `frontend/src/components/AddFieldWithMap.workspace.test.tsx:4` ← `AddFieldWithMap`
  - `frontend/src/components/FieldDetailPanel.tsx:2` ← `FieldDetailPanel`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf:66` ← `/api/v1/`
  - `nginx/nginx.fixed.conf:30` ← `platform_backend`
  - `nginx/nginx.v9.conf:72` ← `/api/v1/`
  - `nginx/nginx.v9.conf:80` ← `platform_backend`

### `raster-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 24 match(es)
  - `frontend/src/components/FieldIndicatorMap.static.test.ts:5` ← `FieldIndicatorMap`
  - `frontend/src/components/FieldIndicatorMap.tsx:292` ← `cdse-tilejson`
  - `frontend/src/components/FieldIndicatorMap.tsx:32` ← `tilejson`
  - `frontend/src/components/FieldIndicatorMap.tsx:2` ← `FieldIndicatorMap`
  - `frontend/src/components/fieldhealth/ScoutingMap.tsx:22` ← `FieldIndicatorMap`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf:65` ← `/api/raster/`
  - `nginx/nginx.fixed.conf:26` ← `raster_backend`
  - `nginx/nginx.v9.conf:246` ← `/api/raster/`
  - `nginx/nginx.v9.conf:87` ← `raster_backend`

### `vegetation-analysis-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 97 match(es)
  - `frontend/src/App.tsx:123` ← `FieldRanking`
  - `frontend/src/components/NDVIGauge.tsx:1` ← `NDVI`
  - `frontend/src/components/approvals/DecisionEvidencePanel.tsx:29` ← `vegetation`
  - `frontend/src/components/ds/tokens.ts:10` ← `NDVI`
  - `frontend/src/components/fieldhealth/DateScrubber.tsx:10` ← `vegetation`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf:64` ← `/api/vegetation/`
  - `nginx/nginx.fixed.conf:23` ← `vegetation_backend`
  - `nginx/nginx.v9.conf:224` ← `/api/vegetation/`
  - `nginx/nginx.v9.conf:84` ← `vegetation_backend`

### `indicators-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 30 match(es)
  - `frontend/src/App.tsx:65` ← `HybridIndexPage`
  - `frontend/src/App.tsx:145` ← `indicators`
  - `frontend/src/components/insights/MapIndicatorLegend.test.tsx:28` ← `indicators`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts:112` ← `indicators`
  - `frontend/src/config/endpoints.ts:57` ← `indicators`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf:66` ← `/api/indicators/`
  - `nginx/nginx.fixed.conf:24` ← `indicators_backend`
  - `nginx/nginx.v9.conf:219` ← `/api/indicators/`
  - `nginx/nginx.v9.conf:83` ← `indicators_backend`

### `weather-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 16 match(es)
  - `frontend/src/App.tsx:102` ← `WeatherAdvice`
  - `frontend/src/components/maphub/weather/README.md:17` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/README.md:20` ← `WeatherProbePopup`
  - `frontend/src/components/maphub/weather/WeatherActionLifecycle.static.test.ts:6` ← `WeatherProbePopup`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts:7` ← `WeatherTileLayer`
- platform-proxy: 306 match(es)
  - `services/sahool-platform/api/agronomic_consistency.py:146` ← `weather`
  - `services/sahool-platform/api/agronomic_replay.py:8` ← `weather`
  - `services/sahool-platform/api/alert_rules.py:9` ← `weather`
  - `services/sahool-platform/api/analytics_shapers.py:79` ← `weather`
  - `services/sahool-platform/api/api_models.py:284` ← `weather`

### `soil-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 152 match(es)
  - `frontend/src/App.tsx:438` ← `soil`
  - `frontend/src/components/AddFieldWithMap.tsx:115` ← `soil`
  - `frontend/src/components/AddFieldWithMap.tsx:410` ← `Soil`
  - `frontend/src/components/FieldDetailPanel.tsx:17` ← `soil`
  - `frontend/src/components/decision/DecisionDeepPanel.tsx:21` ← `soil`
- platform-proxy: 282 match(es)
  - `services/sahool-platform/README.md:36` ← `soil`
  - `services/sahool-platform/api/agronomic_consistency.py:74` ← `soil`
  - `services/sahool-platform/api/alert_rules.py:112` ← `soil`
  - `services/sahool-platform/api/analytics_shapers.py:79` ← `soil`
  - `services/sahool-platform/api/api_models.py:242` ← `soil`

### `field-segmentation` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 7 match(es)
  - `frontend/src/components/AddFieldWithMap.tsx:26` ← `segmentField`
  - `frontend/src/components/AddFieldWithMap.tsx:29` ← `AutoSegmentControl`
  - `frontend/src/components/maphub/AutoSegmentControl.tsx:2` ← `AutoSegmentControl`
  - `frontend/src/services/api.test.ts:41` ← `segmentField`
  - `frontend/src/services/api.test.ts:176` ← `/api/segmentation`
- platform-proxy: 8 match(es)
  - `services/sahool-platform/api/field_geometry_save_guard.py:47` ← `segmentation`
  - `services/sahool-platform/api/routers/service_proxy.py:174` ← `SEGMENTATION_URL`
  - `services/sahool-platform/api/routers/service_proxy.py:162` ← `/api/segmentation/`
  - `services/sahool-platform/api/routers/service_proxy.py:162` ← `segmentation`
  - `services/sahool-platform/tests/test_p0_5_decision_sor_final_certification_guard.py:88` ← `/api/segmentation/`

### `sam2-inference` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 33 match(es)
  - `services/field-segmentation/exg_preprocess.py:236` ← `sam2`
  - `services/field-segmentation/main.py:12` ← `SEGMENTATION_INFERENCE_URL`
  - `services/field-segmentation/main.py:12` ← `SEGMENTATION_BACKEND`
  - `services/field-segmentation/main.py:28` ← `sam2`
  - `services/field-segmentation/test_exg_preprocess.py:7` ← `sam2`

### `ai_agronomist` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 18 match(es)
  - `frontend/src/App.tsx:64` ← `ChatbotPage`
  - `frontend/src/hooks/fieldViewUiWide.static.test.ts:18` ← `ChatbotPage`
  - `frontend/src/hooks/useApi.ts:1982` ← `ai-agronomist`
  - `frontend/src/lib/approvalsConsole.test.ts:26` ← `ChatbotPage`
  - `frontend/src/sections/ChatbotAgronomyPanels.v615.static.test.ts:6` ← `ChatbotPage`
- gateway: 2 match(es)
  - `nginx/nginx.v9.conf:359` ← `/api/ai-agronomist/`
  - `nginx/nginx.v9.conf:95` ← `ai_agronomist_backend`

### `rag-retrieval` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 16 match(es)
  - `services/ai_agronomist/ai_evidence_runtime.py:41` ← `RAG_BASE_URL`
  - `services/ai_agronomist/ai_evidence_runtime.py:41` ← `rag-retrieval`
  - `services/ai_agronomist/main.py:34` ← `RAG_BASE_URL`
  - `services/ai_agronomist/main.py:34` ← `rag-retrieval`
  - `tests_v9/test_gateway_trusted_identity_sec3.py:288` ← `rag-retrieval`

### `knowledge-graph` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 20 match(es)
  - `services/ai_agronomist/ai_evidence_runtime.py:42` ← `KNOWLEDGE_GRAPH_URL`
  - `services/ai_agronomist/ai_evidence_runtime.py:42` ← `knowledge-graph`
  - `services/ai_agronomist/main.py:35` ← `KNOWLEDGE_GRAPH_URL`
  - `services/ai_agronomist/main.py:35` ← `knowledge-graph`
  - `services/mcp_servers/generic_context_server.py:117` ← `knowledge-graph`

### `supervisor-agent` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 20 match(es)
  - `frontend/src/hooks/useApi.ts:248` ← `/api/agent`
  - `frontend/src/hooks/useApi.ts:248` ← `supervisor`
  - `frontend/src/hooks/useApi.ts:248` ← `agent`
  - `frontend/src/lib/designSystemGovernance.test.ts:9` ← `agent`
  - `frontend/src/lib/designSystemGovernance.ts:10` ← `agent`
- gateway: 8 match(es)
  - `nginx/nginx.fixed.conf:60` ← `/api/agent/`
  - `nginx/nginx.fixed.conf:21` ← `supervisor_backend`
  - `nginx/nginx.light.conf:76` ← `/api/agent/`
  - `nginx/nginx.light.conf:34` ← `supervisor_backend`
  - `nginx/nginx.unified.conf:85` ← `/api/agent/`

### `guardrails-engine` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 105 match(es)
  - `frontend/src/App.tsx:148` ← `approval`
  - `frontend/src/components/AddFieldWithMap.tsx:32` ← `validate`
  - `frontend/src/components/AddFieldWithMap.undoredo.test.tsx:53` ← `validate`
  - `frontend/src/components/AddFieldWithMap.workspace.test.tsx:18` ← `validate`
  - `frontend/src/components/AddSeasonWithStages.tsx:104` ← `validate`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf:63` ← `/api/guardrails/`
  - `nginx/nginx.fixed.conf:22` ← `guardrails_backend`
  - `nginx/nginx.v9.conf:336` ← `/api/guardrails/`
  - `nginx/nginx.v9.conf:92` ← `guardrails_backend`

### `agriai-engine` — pass
classification: `experimental-model-runtime`
wiring disposition: `intentional-unconsumed`
wired: `False`
reopen trigger: `SIM-GOLDEN-01 certification plus eligible real-season data`
- activation-safety-contract: 16 match(es)
  - `services/agriai-engine/aquacrop_adapter.py:122` ← `AGRIAI_PRODUCTION_MODE`
  - `services/agriai-engine/aquacrop_adapter.py:251` ← `uncalibrated_pending_golden`
  - `services/agriai-engine/main.py:69` ← `AGRIAI_PRODUCTION_MODE`
  - `services/agriai-engine/simulation_capability.py:80` ← `SIM_PCSE_ENABLED`
  - `services/agriai-engine/simulation_capability.py:88` ← `uncalibrated_pending_golden`

### `mcp_servers` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 95 match(es)
  - `services/supervisor-agent/advisory_skill.py:9` ← `MCP`
  - `services/supervisor-agent/circuit_breaker.py:2` ← `MCP`
  - `services/supervisor-agent/crop_model_skill.py:10` ← `MCP`
  - `services/supervisor-agent/main.py:14` ← `MCP`
  - `services/supervisor-agent/main.py:71` ← `sentinel`

### `actuator-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 195 match(es)
  - `frontend/src/App.tsx:146` ← `irrigation`
  - `frontend/src/components/AddFieldWithMap.tsx:119` ← `irrigation`
  - `frontend/src/components/AddSeasonWithStages.tsx:29` ← `irrigation`
  - `frontend/src/components/FieldDetailPanel.tsx:153` ← `irrigation`
  - `frontend/src/components/decision/DecisionDeepPanel.tsx:21` ← `irrigation`
- internal-consumer: 7 match(es)
  - `services/actuator-service/actuator_runtime.py:161` ← `ACTUATOR_DISPATCH_ADAPTER_ID`
  - `services/actuator-service/actuator_runtime.py:289` ← `/v1/execution-requests/recovery`
  - `services/actuator-service/test_dispatch_bridge.py:174` ← `/v1/execution-requests/recovery`
  - `services/decision-service/main.py:1672` ← `/v1/execution-requests/recovery`
  - `services/decision-service/main.py:62` ← `list_inflight_execution_requests`

### `edge-inference` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 128 match(es)
  - `frontend/src/App.tsx:146` ← `pest`
  - `frontend/src/App.tsx:149` ← `yield`
  - `frontend/src/components/AddSeasonWithStages.tsx:31` ← `yield`
  - `frontend/src/components/FieldDetailPanel.tsx:168` ← `yield`
  - `frontend/src/components/decision/DecisionDeepPanel.tsx:21` ← `pest`
- platform-proxy: 3 match(es)
  - `services/sahool-platform/api/routers/service_proxy.py:142` ← `EDGE_INFERENCE_URL`
  - `services/sahool-platform/api/routers/service_proxy.py:141` ← `edge-inference`
  - `services/sahool-platform/core/capabilities.py:11` ← `edge-inference`

### `video-processor` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 32 match(es)
  - `frontend/src/App.tsx:98` ← `DevicesPage`
  - `frontend/src/components/approvals/DecisionEvidencePanel.tsx:26` ← `snapshot`
  - `frontend/src/components/fieldview/DistrictsWeatherCard.tsx:375` ← `stream`
  - `frontend/src/components/fieldview/EvidenceHistoryCard.tsx:49` ← `snapshot`
  - `frontend/src/components/fieldview/MpcGovernanceCard.tsx:26` ← `snapshot`
- gateway: 6 match(es)
  - `nginx/nginx.light.conf:84` ← `/api/video/`
  - `nginx/nginx.light.conf:35` ← `video_backend`
  - `nginx/nginx.unified.conf:116` ← `/api/video/`
  - `nginx/nginx.unified.conf:40` ← `video_backend`
  - `nginx/nginx.v9.conf:462` ← `/api/video/`

### `weather-polygon-worker` — pass
classification: `ui-indirect`
wiring disposition: `consumed`
wired: `True`
- ui: 7 match(es)
  - `frontend/src/components/maphub/weather/README.md:17` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts:7` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts:24` ← `operation-tile-data`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts:23` ← `tile-data`
  - `frontend/src/components/maphub/weather/WeatherRasterOverlay.tsx:19` ← `WeatherTileLayer`
- internal-consumer: 11 match(es)
  - `services/sahool-platform/core/weather_overlay_pipeline.py:4` ← `field_weather_overlay`
  - `services/sahool-platform/core/weather_overlay_pipeline.py:1` ← `weather_overlay_pipeline`
  - `services/sahool-platform/core/weather_overlay_pipeline.py:1` ← `weather-polygon-worker`
  - `services/sahool-platform/tests/test_weather_overlay_pipeline.py:1` ← `weather_overlay_pipeline`
  - `services/sahool-platform/tests/test_weather_overlay_pipeline.py:1` ← `weather-polygon-worker`

### `weather-signal-engine` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 20 match(es)
  - `services/sahool-platform/api/field_season_projection.py:115` ← `weather_signals`
  - `services/sahool-platform/api/routers/agro_intelligence.py:30` ← `weather_signals`
  - `services/sahool-platform/api/routers/agro_intelligence.py:14` ← `decision_playbook`
  - `services/sahool-platform/core/decision_playbook.py:12` ← `weather_signals`
  - `services/sahool-platform/core/decision_playbook.py:1` ← `decision_playbook`

### `erp-bridge` — pass
classification: `integration`
wiring disposition: `consumed`
wired: `True`
- gateway-or-internal: 19 match(es)
  - `nginx/nginx.unified.conf:145` ← `/api/erp/`
  - `nginx/nginx.unified.conf:46` ← `erp-bridge`
  - `services/mcp_servers/market_server.py:31` ← `ERP_BRIDGE_URL`
  - `services/mcp_servers/market_server.py:31` ← `erp-bridge`
  - `services/mcp_servers/market_server.py:31` ← `sahool-erp-bridge`

### `tts-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 10 match(es)
  - `frontend/src/components/SpeakButton.tsx:1` ← `SpeakButton`
  - `frontend/src/components/SpeakButton.tsx:2` ← `synthesize`
  - `frontend/src/components/SpeakButton.tsx:2` ← `tts`
  - `frontend/src/components/SpeakButton.tsx:6` ← `synthesizeSpeech`
  - `frontend/src/lib/fieldObjectiveHiddenGaps.test.ts:18` ← `synthesize`

### `local-ai-rag` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 64 match(es)
  - `services/supervisor-agent/advisory_skill.py:34` ← `RAG`
  - `services/supervisor-agent/test_ai_orchestration_forensic.py:89` ← `LOCAL_AI_RAG_URL`
  - `services/supervisor-agent/test_ai_orchestration_forensic.py:89` ← `RAG`
  - `services/supervisor-agent/skills/advisory_skill.py:10` ← `LOCAL_AI_RAG_URL`
  - `services/supervisor-agent/skills/advisory_skill.py:9` ← `local-ai-rag`

### `raster-tiler-service` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 45 match(es)
  - `services/raster-service/cloud_native_catalog.py:97` ← `tilejson`
  - `services/raster-service/main.py:48` ← `TITILER_URL`
  - `services/raster-service/raster_cdse_tile_runtime.py:209` ← `tilejson`
  - `services/raster-service/raster_field_runtime.py:61` ← `TITILER_URL`
  - `services/raster-service/raster_job_orchestration.py:198` ← `tilejson`

### `qdrant-seed` — pass
classification: `job`
wiring disposition: `standalone-job`
wired: `None`
- job-contract: 19 match(es)
  - `docker-compose.v9.yml:1692` ← `qdrant-seed`
  - `docker-compose.v9.yml:393` ← `QDRANT`
  - `docker-compose.fixed.yml:257` ← `qdrant-seed`
  - `docker-compose.fixed.yml:19` ← `QDRANT`
  - `docker-compose.rag-kg-mcp.yml:10` ← `QDRANT`

### `decision-service` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 26 match(es)
  - `services/sahool-platform/api/crop_decision_bridge.py:38` ← `decision_service_client`
  - `services/sahool-platform/api/decision_service_client.py:16` ← `DECISION_SERVICE_URL`
  - `services/sahool-platform/api/decision_service_client.py:16` ← `sahool-decision-service`
  - `services/sahool-platform/api/irrigation_activation_gate.py:70` ← `DECISION_SERVICE_URL`
  - `services/sahool-platform/api/irrigation_activation_gate.py:70` ← `sahool-decision-service`

### `model-registry-adapter` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 6 match(es)
  - `services/model-registry-adapter/runtime.py:67` ← `DECISION_SERVICE_URL`
  - `services/model-registry-adapter/worker.py:15` ← `DECISION_SERVICE_URL`
  - `services/model-registry-adapter/tests/test_runtime_contract.py:32` ← `DECISION_SERVICE_URL`
  - `docker-compose.v9.yml:542` ← `DECISION_SERVICE_URL`
  - `docker-compose.v9.yml:1392` ← `sahool-model-registry-worker`

### `gis-workflow-service` — pass
classification: `batch-job-tool`
wiring disposition: `standalone-job`
wired: `None`
- job-contract: 2 match(es)
  - `services/gis-workflow-service/tests/test_run_bundle.py:16` ← `run_bundle`
  - `.github/workflows/gis-workflow-service-gates.yml:6` ← `gis-workflow-service`

### `remote-sensing-workspace-bff` — pass
classification: `ui-bff`
wiring disposition: `consumed`
wired: `True`
- ui-and-gateway-consumer: 6 match(es)
  - `frontend/src/sections/FieldWorkspaceImageryPanel.tsx:8` ← `getRemoteSensingWorkspaceOverview`
  - `frontend/src/services/api/remoteSensingWorkspace.ts:28` ← `getRemoteSensingWorkspaceOverview`
  - `frontend/src/services/api/remoteSensingWorkspace.ts:33` ← `/api/remote-sensing-workspace/`
  - `frontend/nginx.conf:116` ← `/api/remote-sensing-workspace/`
  - `nginx/nginx.v9.conf:266` ← `/api/remote-sensing-workspace/`

### `field-management-service` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 6 match(es)
  - `services/vegetation-analysis-service/test_platform_field_catalog_boundary.py:43` ← `FIELD_SERVICE_URL`
  - `services/vegetation-analysis-service/test_platform_field_catalog_boundary.py:35` ← `/internal/fields`
  - `services/vegetation-analysis-service/vegetation_runtime.py:105` ← `FIELD_SERVICE_URL`
  - `services/vegetation-analysis-service/vegetation_runtime.py:97` ← `/internal/fields`
  - `docker-compose.v9.yml:861` ← `FIELD_SERVICE_URL`

### `scout-ingest-service` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 7 match(es)
  - `services/scout-ingest-service/main.py:334` ← `/internal/ingest/submissions/odk`
  - `services/scout-ingest-service/main.py:2` ← `scout-ingest-service`
  - `services/scout-ingest-service/tests/test_ingest_live.py:1` ← `scout-ingest-service`
  - `docker-compose.v9.yml:549` ← `sahool-scout-ingest`
  - `docker-compose.v9.yml:935` ← `scout-ingest-service`
