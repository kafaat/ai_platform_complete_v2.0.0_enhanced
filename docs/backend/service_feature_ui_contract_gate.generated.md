# service-feature-ui-contract-gate report

- services: 33
- passed: 33
- failed: 0

## Service evidence

### `auth` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 157 match(es)
  - `frontend/src/App.tsx:53` ← `LoginPage`
  - `frontend/src/App.tsx:54` ← `SignupPage`
  - `frontend/src/components/ReferenceQueryState.tsx:7` ← `refresh`
  - `frontend/src/components/fieldview/NdviUnavailableNotice.tsx:21` ← `refresh`
  - `frontend/src/components/maphub/ImageryAutoRefreshGuard.static.test.ts:11` ← `refresh`
- gateway: 8 match(es)
  - `nginx/nginx.fixed.conf:60` ← `/auth/`
  - `nginx/nginx.fixed.conf:29` ← `auth_backend`
  - `nginx/nginx.light.conf:82` ← `/auth/`
  - `nginx/nginx.light.conf:42` ← `auth_backend`
  - `nginx/nginx.unified.conf:91` ← `/auth/`

### `sahool-platform` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 388 match(es)
  - `frontend/src/components/AddFieldWithMap.pivot.behavior.test.tsx:53` ← `AddFieldWithMap`
  - `frontend/src/components/AddFieldWithMap.shapefileImport.test.tsx:26` ← `AddFieldWithMap`
  - `frontend/src/components/AddFieldWithMap.tsx:446` ← `/api/v1`
  - `frontend/src/components/AddFieldWithMap.tsx:2` ← `AddFieldWithMap`
  - `frontend/src/components/AddFieldWithMap.undoredo.test.tsx:6` ← `AddFieldWithMap`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf:77` ← `/api/v1/`
  - `nginx/nginx.fixed.conf:39` ← `platform_backend`
  - `nginx/nginx.v9.conf:86` ← `/api/v1/`
  - `nginx/nginx.v9.conf:94` ← `platform_backend`

### `raster-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 33 match(es)
  - `frontend/src/components/FieldIndicatorMap.boundary.test.tsx:5` ← `FieldIndicatorMap`
  - `frontend/src/components/FieldIndicatorMap.requests.test.tsx:4` ← `FieldIndicatorMap`
  - `frontend/src/components/FieldIndicatorMap.static.test.ts:5` ← `FieldIndicatorMap`
  - `frontend/src/components/FieldIndicatorMap.tsx:332` ← `cdse-tilejson`
  - `frontend/src/components/FieldIndicatorMap.tsx:35` ← `tilejson`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf:76` ← `/api/raster/`
  - `nginx/nginx.fixed.conf:35` ← `raster_backend`
  - `nginx/nginx.v9.conf:228` ← `/api/raster/`
  - `nginx/nginx.v9.conf:101` ← `raster_backend`

### `vegetation-analysis-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 122 match(es)
  - `frontend/src/App.tsx:121` ← `FieldRanking`
  - `frontend/src/components/FieldIndicatorMap.requests.test.tsx:72` ← `NDVI`
  - `frontend/src/components/NDVIGauge.tsx:1` ← `NDVI`
  - `frontend/src/components/approvals/DecisionEvidencePanel.tsx:29` ← `vegetation`
  - `frontend/src/components/ds/tokens.ts:10` ← `NDVI`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf:75` ← `/api/vegetation/`
  - `nginx/nginx.fixed.conf:32` ← `vegetation_backend`
  - `nginx/nginx.v9.conf:232` ← `/api/vegetation/`
  - `nginx/nginx.v9.conf:98` ← `vegetation_backend`

### `indicators-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 37 match(es)
  - `frontend/src/App.tsx:64` ← `HybridIndexPage`
  - `frontend/src/App.tsx:143` ← `indicators`
  - `frontend/src/components/maphub/SoilSamplingPlannerPanel.link.test.tsx:14` ← `indicators`
  - `frontend/src/components/maphub/SoilSamplingPlannerPanel.tsx:11` ← `indicators`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts:123` ← `indicators`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf:77` ← `/api/indicators/`
  - `nginx/nginx.fixed.conf:33` ← `indicators_backend`
  - `nginx/nginx.v9.conf:272` ← `/api/indicators/`
  - `nginx/nginx.v9.conf:97` ← `indicators_backend`

### `weather-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 22 match(es)
  - `frontend/src/App.tsx:102` ← `WeatherAdvice`
  - `frontend/src/components/maphub/weather/README.md:17` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/README.md:20` ← `WeatherProbePopup`
  - `frontend/src/components/maphub/weather/WeatherActionLifecycle.static.test.ts:6` ← `WeatherProbePopup`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts:7` ← `WeatherTileLayer`
- platform-proxy: 366 match(es)
  - `services/sahool-platform/api/agronomic_consistency.py:146` ← `weather`
  - `services/sahool-platform/api/agronomic_context_composer.py:365` ← `weather-service`
  - `services/sahool-platform/api/agronomic_context_composer.py:33` ← `weather`
  - `services/sahool-platform/api/agronomic_replay.py:8` ← `weather`
  - `services/sahool-platform/api/alert_rules.py:9` ← `weather`

### `soil-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 200 match(es)
  - `frontend/src/App.tsx:453` ← `soil`
  - `frontend/src/components/AddFieldWithMap.tsx:125` ← `soil`
  - `frontend/src/components/AddFieldWithMap.tsx:426` ← `Soil`
  - `frontend/src/components/FieldDetailPanel.tsx:17` ← `soil`
  - `frontend/src/components/decision/DecisionDeepPanel.tsx:21` ← `soil`
- platform-proxy: 344 match(es)
  - `services/sahool-platform/README.md:36` ← `soil`
  - `services/sahool-platform/api/agronomic_consistency.py:74` ← `soil`
  - `services/sahool-platform/api/agronomic_context_composer.py:33` ← `soil`
  - `services/sahool-platform/api/agronomic_state_consumers.py:113` ← `soil`
  - `services/sahool-platform/api/alert_rules.py:112` ← `soil`

### `field-segmentation` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 7 match(es)
  - `frontend/src/components/AddFieldWithMap.tsx:26` ← `segmentField`
  - `frontend/src/components/AddFieldWithMap.tsx:29` ← `AutoSegmentControl`
  - `frontend/src/components/maphub/AutoSegmentControl.tsx:2` ← `AutoSegmentControl`
  - `frontend/src/services/api.test.ts:41` ← `segmentField`
  - `frontend/src/services/api.test.ts:180` ← `/api/segmentation`
- platform-proxy: 10 match(es)
  - `services/sahool-platform/api/field_geometry_save_guard.py:47` ← `segmentation`
  - `services/sahool-platform/api/routers/service_proxy.py:269` ← `SEGMENTATION_URL`
  - `services/sahool-platform/api/routers/service_proxy.py:256` ← `/api/segmentation/`
  - `services/sahool-platform/api/routers/service_proxy.py:69` ← `segmentation`
  - `services/sahool-platform/tests/test_edge_segmentation_proxy_authorization.py:182` ← `/api/segmentation/`

### `sam2-inference` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 39 match(es)
  - `services/field-segmentation/exg_preprocess.py:236` ← `sam2`
  - `services/field-segmentation/main.py:12` ← `SEGMENTATION_INFERENCE_URL`
  - `services/field-segmentation/main.py:12` ← `SEGMENTATION_BACKEND`
  - `services/field-segmentation/main.py:28` ← `sam2`
  - `services/field-segmentation/test_exg_preprocess.py:7` ← `sam2`

### `ai_agronomist` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 24 match(es)
  - `frontend/src/App.tsx:63` ← `ChatbotPage`
  - `frontend/src/hooks/fieldViewUiWide.static.test.ts:18` ← `ChatbotPage`
  - `frontend/src/hooks/useApi.ts:2029` ← `ai-agronomist`
  - `frontend/src/lib/approvalsConsole.test.ts:26` ← `ChatbotPage`
  - `frontend/src/sections/ChatbotAgronomyPanels.v615.static.test.ts:6` ← `ChatbotPage`
- gateway: 2 match(es)
  - `nginx/nginx.v9.conf:428` ← `/api/ai-agronomist/`
  - `nginx/nginx.v9.conf:109` ← `ai_agronomist_backend`

### `rag-retrieval` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 46 match(es)
  - `services/ai_agronomist/ai_evidence_runtime.py:60` ← `RAG_BASE_URL`
  - `services/ai_agronomist/ai_evidence_runtime.py:60` ← `rag-retrieval`
  - `services/ai_agronomist/main.py:37` ← `RAG_BASE_URL`
  - `services/ai_agronomist/main.py:37` ← `rag-retrieval`
  - `tests_v9/test_ai_rag_delta_p0.py:317` ← `rag-retrieval`

### `knowledge-graph` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 28 match(es)
  - `services/ai_agronomist/ai_evidence_runtime.py:61` ← `KNOWLEDGE_GRAPH_URL`
  - `services/ai_agronomist/ai_evidence_runtime.py:61` ← `knowledge-graph`
  - `services/ai_agronomist/main.py:38` ← `KNOWLEDGE_GRAPH_URL`
  - `services/ai_agronomist/main.py:38` ← `knowledge-graph`
  - `services/mcp_servers/generic_context_server.py:18` ← `knowledge-graph`

### `supervisor-agent` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 23 match(es)
  - `frontend/src/hooks/useApi.ts:263` ← `/api/agent`
  - `frontend/src/hooks/useApi.ts:263` ← `supervisor`
  - `frontend/src/hooks/useApi.ts:263` ← `agent`
  - `frontend/src/lib/designSystemGovernance.test.ts:9` ← `agent`
  - `frontend/src/lib/designSystemGovernance.ts:10` ← `agent`
- gateway: 8 match(es)
  - `nginx/nginx.fixed.conf:71` ← `/api/agent/`
  - `nginx/nginx.fixed.conf:30` ← `supervisor_backend`
  - `nginx/nginx.light.conf:95` ← `/api/agent/`
  - `nginx/nginx.light.conf:43` ← `supervisor_backend`
  - `nginx/nginx.unified.conf:104` ← `/api/agent/`

### `guardrails-engine` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 180 match(es)
  - `frontend/src/App.tsx:146` ← `approval`
  - `frontend/src/components/AddFieldWithMap.pivot.behavior.test.tsx:41` ← `validate`
  - `frontend/src/components/AddFieldWithMap.shapefileImport.test.tsx:18` ← `validate`
  - `frontend/src/components/AddFieldWithMap.tsx:32` ← `validate`
  - `frontend/src/components/AddFieldWithMap.undoredo.test.tsx:53` ← `validate`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf:74` ← `/api/guardrails/`
  - `nginx/nginx.fixed.conf:31` ← `guardrails_backend`
  - `nginx/nginx.v9.conf:390` ← `/api/guardrails/`
  - `nginx/nginx.v9.conf:106` ← `guardrails_backend`

### `agriai-engine` — pass
classification: `experimental-model-runtime`
wiring disposition: `intentional-unconsumed`
wired: `False`
reopen trigger: `SIM-GOLDEN-01 certification plus eligible real-season data`
- activation-safety-contract: 25 match(es)
  - `services/agriai-engine/aquacrop_adapter.py:180` ← `AGRIAI_PRODUCTION_MODE`
  - `services/agriai-engine/aquacrop_adapter.py:325` ← `uncalibrated_pending_golden`
  - `services/agriai-engine/main.py:72` ← `AGRIAI_PRODUCTION_MODE`
  - `services/agriai-engine/simulation_capability.py:86` ← `SIM_PCSE_ENABLED`
  - `services/agriai-engine/simulation_capability.py:104` ← `uncalibrated_pending_golden`

### `mcp_servers` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 123 match(es)
  - `services/supervisor-agent/circuit_breaker.py:2` ← `MCP`
  - `services/supervisor-agent/main.py:16` ← `MCP`
  - `services/supervisor-agent/main.py:75` ← `sentinel`
  - `services/supervisor-agent/mcp_client.py:3` ← `MCP`
  - `services/supervisor-agent/router.py:92` ← `sentinel`

### `actuator-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 352 match(es)
  - `frontend/src/App.tsx:144` ← `irrigation`
  - `frontend/src/components/AddFieldWithMap.pivot.behavior.test.tsx:111` ← `irrigation`
  - `frontend/src/components/AddFieldWithMap.tsx:129` ← `irrigation`
  - `frontend/src/components/AddSeasonWithStages.tsx:32` ← `irrigation`
  - `frontend/src/components/FieldDetailPanel.tsx:153` ← `irrigation`
- internal-consumer: 8 match(es)
  - `services/actuator-service/actuator_runtime.py:176` ← `ACTUATOR_DISPATCH_ADAPTER_ID`
  - `services/actuator-service/actuator_runtime.py:341` ← `/v1/execution-requests/recovery`
  - `services/actuator-service/test_dispatch_bridge.py:204` ← `/v1/execution-requests/recovery`
  - `services/decision-service/main.py:1965` ← `/v1/execution-requests/recovery`
  - `services/decision-service/main.py:69` ← `list_inflight_execution_requests`

### `edge-inference` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 196 match(es)
  - `frontend/src/App.tsx:144` ← `pest`
  - `frontend/src/App.tsx:147` ← `yield`
  - `frontend/src/components/AddSeasonWithStages.tsx:34` ← `yield`
  - `frontend/src/components/FieldDetailPanel.tsx:168` ← `yield`
  - `frontend/src/components/decision/DecisionDeepPanel.tsx:21` ← `pest`
- platform-proxy: 3 match(es)
  - `services/sahool-platform/api/routers/service_proxy.py:233` ← `EDGE_INFERENCE_URL`
  - `services/sahool-platform/api/routers/service_proxy.py:59` ← `edge-inference`
  - `services/sahool-platform/core/capabilities.py:11` ← `edge-inference`

### `video-processor` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 102 match(es)
  - `frontend/src/App.tsx:98` ← `DevicesPage`
  - `frontend/src/components/approvals/DecisionEvidencePanel.tsx:26` ← `snapshot`
  - `frontend/src/components/fieldsetup/YieldStep.test.tsx:1` ← `stream`
  - `frontend/src/components/fieldview/DistrictsWeatherCard.tsx:376` ← `stream`
  - `frontend/src/components/fieldview/EvidenceHistoryCard.tsx:49` ← `snapshot`
- gateway: 6 match(es)
  - `nginx/nginx.light.conf:103` ← `/api/video/`
  - `nginx/nginx.light.conf:44` ← `video_backend`
  - `nginx/nginx.unified.conf:135` ← `/api/video/`
  - `nginx/nginx.unified.conf:49` ← `video_backend`
  - `nginx/nginx.v9.conf:588` ← `/api/video/`

### `weather-signal-engine` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 24 match(es)
  - `services/sahool-platform/api/field_season_projection.py:121` ← `weather_signals`
  - `services/sahool-platform/api/routers/agro_intelligence.py:30` ← `weather_signals`
  - `services/sahool-platform/api/routers/agro_intelligence.py:14` ← `decision_playbook`
  - `services/sahool-platform/core/decision_playbook.py:12` ← `weather_signals`
  - `services/sahool-platform/core/decision_playbook.py:1` ← `decision_playbook`

### `erp-bridge` — pass
classification: `integration`
wiring disposition: `consumed`
wired: `True`
- gateway-or-internal: 30 match(es)
  - `nginx/nginx.unified.conf:169` ← `/api/erp/`
  - `nginx/nginx.unified.conf:55` ← `erp-bridge`
  - `services/mcp_servers/market_server.py:38` ← `ERP_BRIDGE_URL`
  - `services/mcp_servers/market_server.py:38` ← `erp-bridge`
  - `services/mcp_servers/market_server.py:38` ← `sahool-erp-bridge`

### `tts-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 13 match(es)
  - `frontend/src/components/SpeakButton.test.tsx:10` ← `SpeakButton`
  - `frontend/src/components/SpeakButton.test.tsx:11` ← `synthesize`
  - `frontend/src/components/SpeakButton.test.tsx:11` ← `synthesizeSpeech`
  - `frontend/src/components/SpeakButton.tsx:1` ← `SpeakButton`
  - `frontend/src/components/SpeakButton.tsx:2` ← `synthesize`

### `local-ai-rag` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 122 match(es)
  - `services/supervisor-agent/main.py:157` ← `RAG`
  - `services/supervisor-agent/mcp_client.py:74` ← `RAG`
  - `services/supervisor-agent/test_ai_orchestration_forensic.py:89` ← `LOCAL_AI_RAG_URL`
  - `services/supervisor-agent/test_ai_orchestration_forensic.py:762` ← `local-ai-rag`
  - `services/supervisor-agent/test_ai_orchestration_forensic.py:89` ← `RAG`

### `raster-tiler-service` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 58 match(es)
  - `services/raster-service/cloud_native_catalog.py:110` ← `tilejson`
  - `services/raster-service/main.py:48` ← `TITILER_URL`
  - `services/raster-service/raster_cdse_tile_runtime.py:654` ← `tilejson`
  - `services/raster-service/raster_field_runtime.py:66` ← `TITILER_URL`
  - `services/raster-service/raster_field_runtime.py:468` ← `tilejson`

### `qdrant-seed` — pass
classification: `job`
wiring disposition: `standalone-job`
wired: `None`
- job-contract: 90 match(es)
  - `docker-compose.v9.yml:619` ← `qdrant-seed`
  - `docker-compose.v9.yml:607` ← `QDRANT`
  - `docker-compose.rag-kg-mcp.yml:12` ← `QDRANT`
  - `tests_v9/conftest.py:32` ← `QDRANT`
  - `tests_v9/redis_txn_double.py:20` ← `collection`

### `decision-service` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 35 match(es)
  - `services/sahool-platform/api/agronomic_context_composer.py:228` ← `decision_service_client`
  - `services/sahool-platform/api/crop_decision_bridge.py:39` ← `decision_service_client`
  - `services/sahool-platform/api/decision_service_client.py:21` ← `DECISION_SERVICE_URL`
  - `services/sahool-platform/api/decision_service_client.py:21` ← `sahool-decision-service`
  - `services/sahool-platform/api/irrigation_activation_gate.py:70` ← `DECISION_SERVICE_URL`

### `model-registry-adapter` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 8 match(es)
  - `services/model-registry-adapter/runtime.py:73` ← `DECISION_SERVICE_URL`
  - `services/model-registry-adapter/runtime.py:70` ← `model-registry`
  - `services/model-registry-adapter/worker.py:19` ← `DECISION_SERVICE_URL`
  - `services/model-registry-adapter/tests/test_claim_recovery.py:66` ← `DECISION_SERVICE_URL`
  - `services/model-registry-adapter/tests/test_runtime_contract.py:32` ← `DECISION_SERVICE_URL`

### `gis-workflow-service` — pass
classification: `batch-job-tool`
wiring disposition: `standalone-job`
wired: `None`
- job-contract: 4 match(es)
  - `services/gis-workflow-service/tests/test_bulletin_bundle_evidence.py:1` ← `run_bundle`
  - `services/gis-workflow-service/tests/test_run_bundle.py:16` ← `run_bundle`
  - `services/gis-workflow-service/tests/test_run_bundle_validity_and_evidence.py:1` ← `run_bundle`
  - `.github/workflows/gis-workflow-service-gates.yml:6` ← `gis-workflow-service`

### `remote-sensing-workspace-bff` — pass
classification: `ui-bff`
wiring disposition: `consumed`
wired: `True`
- ui-and-gateway-consumer: 6 match(es)
  - `frontend/src/sections/FieldWorkspaceImageryPanel.tsx:8` ← `getRemoteSensingWorkspaceOverview`
  - `frontend/src/services/api/remoteSensingWorkspace.ts:33` ← `getRemoteSensingWorkspaceOverview`
  - `frontend/src/services/api/remoteSensingWorkspace.ts:38` ← `/api/remote-sensing-workspace/`
  - `frontend/nginx.conf:314` ← `/api/remote-sensing-workspace/`
  - `nginx/nginx.v9.conf:319` ← `/api/remote-sensing-workspace/`

### `field-management-service` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 6 match(es)
  - `services/vegetation-analysis-service/test_platform_field_catalog_boundary.py:60` ← `FIELD_SERVICE_URL`
  - `services/vegetation-analysis-service/test_platform_field_catalog_boundary.py:42` ← `/internal/fields`
  - `services/vegetation-analysis-service/vegetation_runtime.py:111` ← `FIELD_SERVICE_URL`
  - `services/vegetation-analysis-service/vegetation_runtime.py:103` ← `/internal/fields`
  - `docker-compose.v9.yml:1278` ← `FIELD_SERVICE_URL`

### `realtime-session` — pass
classification: `experimental-realtime-control-plane`
wiring disposition: `consumed`
wired: `True`
reopen trigger: `Feature activation remains blocked pending live SFU admission, actual tenant RLS and network acceptance.`
- activation-safety-contract: 5 match(es)
  - `services/realtime-session/realtime_session/session_runtime.py:34` ← `SAHOOL_REALTIME_ENABLED`
  - `services/realtime-session/realtime_session/session_runtime.py:39` ← `LIVEKIT_AUTO_CREATE_DISABLED`
  - `tests_v9/test_realtime_session_api.py:132` ← `SAHOOL_REALTIME_ENABLED`
  - `tests_v9/test_realtime_session_api.py:131` ← `test_default_service_remains_disabled_and_does_not_issue_tokens`
  - `tests_v9/test_realtime_session_api.py:238` ← `test_other_actor_or_tenant_cannot_read_or_close_session`
- job-contract: 3 match(es)
  - `.github/workflows/realtime-session.yml:1` ← `Realtime Session Foundation`
  - `.github/workflows/realtime-session.yml:43` ← `tests_v9/test_realtime_voice_jobs.py`
  - `services/realtime-session/tests/test_livekit_adapter.py:22` ← `LiveKitGateway`
- ui: 6 match(es)
  - `frontend/src/realtime-call/api.test.ts:26` ← `/api/v1/realtime/sessions`
  - `frontend/src/realtime-call/api.test.ts:26` ← `voice_consent`
  - `frontend/src/realtime-call/api.ts:35` ← `/api/v1/realtime/sessions`
  - `frontend/src/realtime-call/api.ts:36` ← `voice_consent`
  - `mobile/sahool_app/lib/features/realtime/realtime_api.dart:15` ← `/api/v1/realtime/sessions`

### `scout-ingest-service` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 8 match(es)
  - `services/scout-ingest-service/main.py:365` ← `/internal/ingest/submissions/odk`
  - `services/scout-ingest-service/main.py:2` ← `scout-ingest-service`
  - `services/scout-ingest-service/tests/test_ingest_live.py:1` ← `scout-ingest-service`
  - `services/scout-ingest-service/tests/test_media_live.py:48` ← `sahool-scout-ingest`
  - `docker-compose.v9.yml:107` ← `sahool-scout-ingest`

### `realtime-agent` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 3 match(es)
  - `services/realtime-agent/realtime_agent/config.py:68` ← `REALTIME_WORKER_SECRET`
  - `services/realtime-agent/realtime_agent/context.py:160` ← `/api/v1/realtime/internal/jobs/`
  - `services/realtime-agent/realtime_agent/worker.py:24` ← `sahool-agronomist`
