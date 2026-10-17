# service-feature-ui-contract-gate report

- services: 31
- passed: 31
- failed: 0

## Service evidence

### `auth` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 57 match(es)
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
- ui: 221 match(es)
  - `frontend/src/components/AddFieldWithMap.tsx:441` ← `/api/v1`
  - `frontend/src/components/AddFieldWithMap.tsx:2` ← `AddFieldWithMap`
  - `frontend/src/components/AddFieldWithMap.undoredo.test.tsx:6` ← `AddFieldWithMap`
  - `frontend/src/components/AddFieldWithMap.workspace.test.tsx:4` ← `AddFieldWithMap`
  - `frontend/src/components/FieldDetailPanel.tsx:2` ← `FieldDetailPanel`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf:77` ← `/api/v1/`
  - `nginx/nginx.fixed.conf:39` ← `platform_backend`
  - `nginx/nginx.v9.conf:86` ← `/api/v1/`
  - `nginx/nginx.v9.conf:94` ← `platform_backend`

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
  - `nginx/nginx.fixed.conf:76` ← `/api/raster/`
  - `nginx/nginx.fixed.conf:35` ← `raster_backend`
  - `nginx/nginx.v9.conf:228` ← `/api/raster/`
  - `nginx/nginx.v9.conf:101` ← `raster_backend`

### `vegetation-analysis-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 97 match(es)
  - `frontend/src/App.tsx:121` ← `FieldRanking`
  - `frontend/src/components/NDVIGauge.tsx:1` ← `NDVI`
  - `frontend/src/components/approvals/DecisionEvidencePanel.tsx:29` ← `vegetation`
  - `frontend/src/components/ds/tokens.ts:10` ← `NDVI`
  - `frontend/src/components/fieldhealth/DateScrubber.tsx:10` ← `vegetation`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf:75` ← `/api/vegetation/`
  - `nginx/nginx.fixed.conf:32` ← `vegetation_backend`
  - `nginx/nginx.v9.conf:232` ← `/api/vegetation/`
  - `nginx/nginx.v9.conf:98` ← `vegetation_backend`

### `indicators-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 32 match(es)
  - `frontend/src/App.tsx:64` ← `HybridIndexPage`
  - `frontend/src/App.tsx:143` ← `indicators`
  - `frontend/src/components/insights/MapIndicatorLegend.test.tsx:28` ← `indicators`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts:123` ← `indicators`
  - `frontend/src/config/endpoints.ts:61` ← `indicators`
- gateway: 4 match(es)
  - `nginx/nginx.fixed.conf:77` ← `/api/indicators/`
  - `nginx/nginx.fixed.conf:33` ← `indicators_backend`
  - `nginx/nginx.v9.conf:272` ← `/api/indicators/`
  - `nginx/nginx.v9.conf:97` ← `indicators_backend`

### `weather-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 17 match(es)
  - `frontend/src/App.tsx:102` ← `WeatherAdvice`
  - `frontend/src/components/maphub/weather/README.md:17` ← `WeatherTileLayer`
  - `frontend/src/components/maphub/weather/README.md:20` ← `WeatherProbePopup`
  - `frontend/src/components/maphub/weather/WeatherActionLifecycle.static.test.ts:6` ← `WeatherProbePopup`
  - `frontend/src/components/maphub/weather/WeatherEngine.static.test.ts:7` ← `WeatherTileLayer`
- platform-proxy: 336 match(es)
  - `services/sahool-platform/api/agronomic_consistency.py:146` ← `weather`
  - `services/sahool-platform/api/agronomic_context_composer.py:32` ← `weather`
  - `services/sahool-platform/api/agronomic_replay.py:8` ← `weather`
  - `services/sahool-platform/api/alert_rules.py:9` ← `weather`
  - `services/sahool-platform/api/analytics_shapers.py:79` ← `weather`

### `soil-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 154 match(es)
  - `frontend/src/App.tsx:437` ← `soil`
  - `frontend/src/components/AddFieldWithMap.tsx:118` ← `soil`
  - `frontend/src/components/AddFieldWithMap.tsx:421` ← `Soil`
  - `frontend/src/components/FieldDetailPanel.tsx:17` ← `soil`
  - `frontend/src/components/decision/DecisionDeepPanel.tsx:21` ← `soil`
- platform-proxy: 320 match(es)
  - `services/sahool-platform/README.md:36` ← `soil`
  - `services/sahool-platform/api/agronomic_consistency.py:74` ← `soil`
  - `services/sahool-platform/api/agronomic_context_composer.py:32` ← `soil`
  - `services/sahool-platform/api/agronomic_state_consumers.py:105` ← `soil`
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
  - `frontend/src/services/api.test.ts:178` ← `/api/segmentation`
- platform-proxy: 8 match(es)
  - `services/sahool-platform/api/field_geometry_save_guard.py:47` ← `segmentation`
  - `services/sahool-platform/api/routers/service_proxy.py:217` ← `SEGMENTATION_URL`
  - `services/sahool-platform/api/routers/service_proxy.py:205` ← `/api/segmentation/`
  - `services/sahool-platform/api/routers/service_proxy.py:205` ← `segmentation`
  - `services/sahool-platform/tests/test_p0_5_decision_sor_final_certification_guard.py:88` ← `/api/segmentation/`

### `sam2-inference` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 36 match(es)
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
  - `frontend/src/App.tsx:63` ← `ChatbotPage`
  - `frontend/src/hooks/fieldViewUiWide.static.test.ts:18` ← `ChatbotPage`
  - `frontend/src/hooks/useApi.ts:1981` ← `ai-agronomist`
  - `frontend/src/lib/approvalsConsole.test.ts:26` ← `ChatbotPage`
  - `frontend/src/sections/ChatbotAgronomyPanels.v615.static.test.ts:6` ← `ChatbotPage`
- gateway: 2 match(es)
  - `nginx/nginx.v9.conf:428` ← `/api/ai-agronomist/`
  - `nginx/nginx.v9.conf:109` ← `ai_agronomist_backend`

### `rag-retrieval` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 43 match(es)
  - `services/ai_agronomist/ai_evidence_runtime.py:56` ← `RAG_BASE_URL`
  - `services/ai_agronomist/ai_evidence_runtime.py:56` ← `rag-retrieval`
  - `services/ai_agronomist/main.py:36` ← `RAG_BASE_URL`
  - `services/ai_agronomist/main.py:36` ← `rag-retrieval`
  - `tests_v9/test_ai_rag_delta_p0.py:317` ← `rag-retrieval`

### `knowledge-graph` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 27 match(es)
  - `services/ai_agronomist/ai_evidence_runtime.py:57` ← `KNOWLEDGE_GRAPH_URL`
  - `services/ai_agronomist/ai_evidence_runtime.py:57` ← `knowledge-graph`
  - `services/ai_agronomist/main.py:37` ← `KNOWLEDGE_GRAPH_URL`
  - `services/ai_agronomist/main.py:37` ← `knowledge-graph`
  - `services/mcp_servers/generic_context_server.py:18` ← `knowledge-graph`

### `supervisor-agent` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 20 match(es)
  - `frontend/src/hooks/useApi.ts:242` ← `/api/agent`
  - `frontend/src/hooks/useApi.ts:242` ← `supervisor`
  - `frontend/src/hooks/useApi.ts:242` ← `agent`
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
- ui: 115 match(es)
  - `frontend/src/App.tsx:146` ← `approval`
  - `frontend/src/components/AddFieldWithMap.tsx:32` ← `validate`
  - `frontend/src/components/AddFieldWithMap.undoredo.test.tsx:53` ← `validate`
  - `frontend/src/components/AddFieldWithMap.workspace.test.tsx:18` ← `validate`
  - `frontend/src/components/AddSeasonWithStages.tsx:104` ← `validate`
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
- activation-safety-contract: 22 match(es)
  - `services/agriai-engine/aquacrop_adapter.py:133` ← `AGRIAI_PRODUCTION_MODE`
  - `services/agriai-engine/aquacrop_adapter.py:262` ← `uncalibrated_pending_golden`
  - `services/agriai-engine/main.py:72` ← `AGRIAI_PRODUCTION_MODE`
  - `services/agriai-engine/simulation_capability.py:86` ← `SIM_PCSE_ENABLED`
  - `services/agriai-engine/simulation_capability.py:104` ← `uncalibrated_pending_golden`

### `mcp_servers` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 111 match(es)
  - `services/supervisor-agent/circuit_breaker.py:2` ← `MCP`
  - `services/supervisor-agent/main.py:14` ← `MCP`
  - `services/supervisor-agent/main.py:73` ← `sentinel`
  - `services/supervisor-agent/mcp_client.py:3` ← `MCP`
  - `services/supervisor-agent/router.py:40` ← `sentinel`

### `actuator-service` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 206 match(es)
  - `frontend/src/App.tsx:144` ← `irrigation`
  - `frontend/src/components/AddFieldWithMap.tsx:122` ← `irrigation`
  - `frontend/src/components/AddSeasonWithStages.tsx:29` ← `irrigation`
  - `frontend/src/components/FieldDetailPanel.tsx:153` ← `irrigation`
  - `frontend/src/components/decision/DecisionDeepPanel.tsx:21` ← `irrigation`
- internal-consumer: 7 match(es)
  - `services/actuator-service/actuator_runtime.py:161` ← `ACTUATOR_DISPATCH_ADAPTER_ID`
  - `services/actuator-service/actuator_runtime.py:289` ← `/v1/execution-requests/recovery`
  - `services/actuator-service/test_dispatch_bridge.py:174` ← `/v1/execution-requests/recovery`
  - `services/decision-service/main.py:1821` ← `/v1/execution-requests/recovery`
  - `services/decision-service/main.py:64` ← `list_inflight_execution_requests`

### `edge-inference` — pass
classification: `ui`
wiring disposition: `consumed`
wired: `True`
- ui: 131 match(es)
  - `frontend/src/App.tsx:144` ← `pest`
  - `frontend/src/App.tsx:147` ← `yield`
  - `frontend/src/components/AddSeasonWithStages.tsx:31` ← `yield`
  - `frontend/src/components/FieldDetailPanel.tsx:168` ← `yield`
  - `frontend/src/components/decision/DecisionDeepPanel.tsx:21` ← `pest`
- platform-proxy: 3 match(es)
  - `services/sahool-platform/api/routers/service_proxy.py:182` ← `EDGE_INFERENCE_URL`
  - `services/sahool-platform/api/routers/service_proxy.py:181` ← `edge-inference`
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
  - `nginx/nginx.light.conf:103` ← `/api/video/`
  - `nginx/nginx.light.conf:44` ← `video_backend`
  - `nginx/nginx.unified.conf:135` ← `/api/video/`
  - `nginx/nginx.unified.conf:49` ← `video_backend`
  - `nginx/nginx.v9.conf:565` ← `/api/video/`

### `weather-signal-engine` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 23 match(es)
  - `services/sahool-platform/api/field_season_projection.py:121` ← `weather_signals`
  - `services/sahool-platform/api/routers/agro_intelligence.py:30` ← `weather_signals`
  - `services/sahool-platform/api/routers/agro_intelligence.py:14` ← `decision_playbook`
  - `services/sahool-platform/core/decision_playbook.py:12` ← `weather_signals`
  - `services/sahool-platform/core/decision_playbook.py:1` ← `decision_playbook`

### `erp-bridge` — pass
classification: `integration`
wiring disposition: `consumed`
wired: `True`
- gateway-or-internal: 26 match(es)
  - `nginx/nginx.unified.conf:169` ← `/api/erp/`
  - `nginx/nginx.unified.conf:55` ← `erp-bridge`
  - `services/mcp_servers/market_server.py:33` ← `ERP_BRIDGE_URL`
  - `services/mcp_servers/market_server.py:33` ← `erp-bridge`
  - `services/mcp_servers/market_server.py:33` ← `sahool-erp-bridge`

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
- internal-consumer: 104 match(es)
  - `services/supervisor-agent/mcp_client.py:74` ← `RAG`
  - `services/supervisor-agent/test_ai_orchestration_forensic.py:89` ← `LOCAL_AI_RAG_URL`
  - `services/supervisor-agent/test_ai_orchestration_forensic.py:89` ← `RAG`
  - `services/supervisor-agent/skills/advisory_skill.py:10` ← `LOCAL_AI_RAG_URL`
  - `services/supervisor-agent/skills/advisory_skill.py:9` ← `local-ai-rag`

### `raster-tiler-service` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 53 match(es)
  - `services/raster-service/cloud_native_catalog.py:104` ← `tilejson`
  - `services/raster-service/main.py:48` ← `TITILER_URL`
  - `services/raster-service/raster_cdse_tile_runtime.py:528` ← `tilejson`
  - `services/raster-service/raster_field_runtime.py:62` ← `TITILER_URL`
  - `services/raster-service/raster_job_orchestration.py:200` ← `tilejson`

### `qdrant-seed` — pass
classification: `job`
wiring disposition: `standalone-job`
wired: `None`
- job-contract: 73 match(es)
  - `docker-compose.v9.yml:480` ← `qdrant-seed`
  - `docker-compose.v9.yml:468` ← `QDRANT`
  - `docker-compose.rag-kg-mcp.yml:10` ← `QDRANT`
  - `tests_v9/conftest.py:32` ← `QDRANT`
  - `tests_v9/test_ai_rag_delta_p0.py:62` ← `qdrant-seed`

### `decision-service` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 33 match(es)
  - `services/sahool-platform/api/crop_decision_bridge.py:38` ← `decision_service_client`
  - `services/sahool-platform/api/decision_service_client.py:21` ← `DECISION_SERVICE_URL`
  - `services/sahool-platform/api/decision_service_client.py:21` ← `sahool-decision-service`
  - `services/sahool-platform/api/irrigation_activation_gate.py:70` ← `DECISION_SERVICE_URL`
  - `services/sahool-platform/api/irrigation_activation_gate.py:70` ← `sahool-decision-service`

### `model-registry-adapter` — pass
classification: `internal`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 7 match(es)
  - `services/model-registry-adapter/runtime.py:72` ← `DECISION_SERVICE_URL`
  - `services/model-registry-adapter/runtime.py:69` ← `model-registry`
  - `services/model-registry-adapter/worker.py:15` ← `DECISION_SERVICE_URL`
  - `services/model-registry-adapter/tests/test_runtime_contract.py:32` ← `DECISION_SERVICE_URL`
  - `docker-compose.v9.yml:748` ← `DECISION_SERVICE_URL`

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
  - `frontend/nginx.conf:284` ← `/api/remote-sensing-workspace/`
  - `nginx/nginx.v9.conf:319` ← `/api/remote-sensing-workspace/`

### `field-management-service` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 6 match(es)
  - `services/vegetation-analysis-service/test_platform_field_catalog_boundary.py:43` ← `FIELD_SERVICE_URL`
  - `services/vegetation-analysis-service/test_platform_field_catalog_boundary.py:35` ← `/internal/fields`
  - `services/vegetation-analysis-service/vegetation_runtime.py:106` ← `FIELD_SERVICE_URL`
  - `services/vegetation-analysis-service/vegetation_runtime.py:98` ← `/internal/fields`
  - `docker-compose.v9.yml:1085` ← `FIELD_SERVICE_URL`

### `scout-ingest-service` — pass
classification: `internal-sensitive`
wiring disposition: `consumed`
wired: `True`
- internal-consumer: 7 match(es)
  - `services/scout-ingest-service/main.py:360` ← `/internal/ingest/submissions/odk`
  - `services/scout-ingest-service/main.py:2` ← `scout-ingest-service`
  - `services/scout-ingest-service/tests/test_ingest_live.py:1` ← `scout-ingest-service`
  - `docker-compose.v9.yml:104` ← `sahool-scout-ingest`
  - `docker-compose.v9.yml:1160` ← `scout-ingest-service`
