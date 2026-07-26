# Static Execution Dependency and Dead-Code Audit

> Repository evidence only. This report does not prove runtime reachability and performs no automatic deletion.

## Summary

- Python files parsed: **1797**
- FastAPI-style route handlers: **1035**
- Static function-call edges: **69830**
- Dead-code candidates: **610**
- Duplicate function groups: **57**
- Automatic deletions: **0**

## Highest-confidence dead-code candidates

| Owner | Symbol | Kind | File | Line |
|---|---|---|---|---:|
| `decision-service` | `_service_token_guard` | function | `services/decision-service/main.py` | 151 |
| `mcp-servers` | `_simulate_wofost` | function | `services/mcp_servers/wofost_server.py` | 233 |
| `raster-service` | `_scene_band_mapping` | function | `services/raster-service/raster_main_compat_exports.py` | 92 |
| `raster-service` | `_bbox_from_geom` | function | `services/raster-service/raster_main_compat_exports.py` | 97 |
| `raster-service` | `_evict_field_layers` | function | `services/raster-service/raster_main_runtime.py` | 46 |
| `raster-service` | `_require_layer_tenant` | function | `services/raster-service/raster_main_runtime.py` | 89 |
| `raster-service` | `_require_layer_tenant_authorized` | function | `services/raster-service/raster_main_runtime.py` | 93 |
| `sahool-platform` | `_apply_tenant_guc` | function | `services/sahool-platform/api/main.py` | 645 |
| `sahool-platform` | `_record_to_json` | function | `services/sahool-platform/api/routers/field_ai_context.py` | 59 |
| `sahool-platform` | `_conflict_changed_fields` | function | `services/sahool-platform/api/routers/fields.py` | 1235 |
| `sahool-platform` | `_weather_tile_interpolation_payload` | function | `services/sahool-platform/api/routers/weather.py` | 417 |
| `sahool-platform` | `_parse_series_hours` | function | `services/sahool-platform/api/routers/weather.py` | 1192 |
| `sahool-platform` | `_time_key_from_hour` | function | `services/sahool-platform/api/routers/weather.py` | 1206 |
| `sahool-platform` | `_best_operation_frame` | function | `services/sahool-platform/api/routers/weather.py` | 1545 |
| `sahool-platform` | `_unavailable_tile_response` | function | `services/sahool-platform/api/routers/weather.py` | 2368 |
| `sahool-platform` | `_irrigation_validate` | function | `services/sahool-platform/api/workflow_definitions.py` | 182 |
| `sahool-platform` | `_irrigation_schedule` | function | `services/sahool-platform/api/workflow_definitions.py` | 188 |
| `sahool-platform` | `_irrigation_execute` | function | `services/sahool-platform/api/workflow_definitions.py` | 194 |
| `sahool-platform` | `_irrigation_verify` | function | `services/sahool-platform/api/workflow_definitions.py` | 200 |
| `sahool-platform` | `_irrigation_real_validate` | function | `services/sahool-platform/api/workflow_definitions.py` | 239 |
| `sahool-platform` | `_irrigation_real_schedule` | function | `services/sahool-platform/api/workflow_definitions.py` | 289 |
| `sahool-platform` | `_irrigation_real_execute` | function | `services/sahool-platform/api/workflow_definitions.py` | 355 |
| `sahool-platform` | `_irrigation_real_execute_compensate` | function | `services/sahool-platform/api/workflow_definitions.py` | 405 |
| `sahool-platform` | `_irrigation_real_verify` | function | `services/sahool-platform/api/workflow_definitions.py` | 419 |
| `sahool-platform` | `_irrigation_real_approval_gate` | function | `services/sahool-platform/api/workflow_definitions.py` | 463 |
| `sahool-platform` | `_irrigation_real_suspend_until_approved` | function | `services/sahool-platform/api/workflow_definitions.py` | 477 |
| `sahool-platform` | `_min_conf` | function | `services/sahool-platform/core/crop_inference.py` | 40 |
| `sahool-platform` | `_patch_engine_gdd` | function | `services/sahool-platform/tests/test_crop_decision_endpoint.py` | 24 |
| `sahool-platform` | `_patch_engine_gdd` | function | `services/sahool-platform/tests/test_crop_twin_compose_endpoint.py` | 24 |
| `sahool-platform` | `_patch_engine_gdd` | function | `services/sahool-platform/tests/test_crop_twin_server_spectral.py` | 20 |
| `sahool-platform` | `_patch_engine_gdd` | function | `services/sahool-platform/tests/test_decision_lineage_endpoints.py` | 31 |
| `sahool-platform` | `_reset_breaker` | function | `services/sahool-platform/tests/test_openmeteo_circuit.py` | 21 |
| `sahool-platform` | `_patch_engine_gdd` | function | `services/sahool-platform/tests/test_profit_aware_decision_endpoint.py` | 25 |
| `sam2-inference` | `_startup` | function | `services/sam2-inference/main.py` | 19 |
| `soil-service` | `_tenant_context_mw` | function | `services/soil-service/main.py` | 107 |
| `shared` | `_normalize_feature_vector` | function | `shared/precision_agriculture/phase6_intelligence.py` | 221 |

## Duplicate implementation groups

| Fingerprint | Occurrences |
|---|---:|
| `00dc80fd51c01661` | 2 |
| `00df9412533ea0ec` | 2 |
| `1b393c046c04c1b3` | 2 |
| `269b85d37e195923` | 2 |
| `2706dd61339afe06` | 3 |
| `2e238855cd34b5bb` | 2 |
| `304f827086942b27` | 5 |
| `31943628afb7968b` | 2 |
| `38a7f4fecdb244ec` | 2 |
| `38fac26497b54c91` | 2 |
| `39520454ba04d116` | 2 |
| `3dd5aa4326908e6c` | 9 |
| `414bdbb9751faa0d` | 2 |
| `418dd134c75a4198` | 2 |
| `56d0386734b32837` | 2 |
| `5a845cb4f426a713` | 2 |
| `5eadbbed142afa2e` | 2 |
| `603e0b55867bb10d` | 4 |
| `6b7bddb925e9b990` | 2 |
| `6d67eb8d03d4b516` | 9 |
| `7105b4bae8a6c92c` | 2 |
| `79c4e44c5402a756` | 2 |
| `7a18605ca524ba04` | 2 |
| `7af9ac732fab3cbb` | 3 |
| `7e8b0636abbc95bd` | 2 |
| `7fe1126431c35111` | 2 |
| `857d341ac91e610b` | 10 |
| `85e033f2a695499c` | 2 |
| `86cc59da6a5b54fc` | 2 |
| `8932397d8cd062c4` | 3 |
| `93be55b4b87abbf2` | 2 |
| `950be0609045232d` | 2 |
| `952c25d8ae321d4d` | 2 |
| `a2f9f7386f96c620` | 2 |
| `a37364d8d551e4f6` | 2 |
| `a40b96b5251f36aa` | 5 |
| `ac66dd3b4393e31b` | 5 |
| `af0fa057ff7366d9` | 2 |
| `b8d801394dbf4f3d` | 2 |
| `baa6814768fbaf1a` | 10 |
| `be832a5993c4c8b6` | 4 |
| `c426e46b262d6007` | 2 |
| `c6570633d45c255b` | 7 |
| `cf4d15a6153b42a9` | 3 |
| `d2d43e0a8e8c7dfa` | 2 |
| `dce437f2a9c84f46` | 2 |
| `dfa39738f5923c2f` | 2 |
| `e1fe2d0b489ce09b` | 2 |
| `e27975739701a0f9` | 2 |
| `eae9c0003b60fda1` | 5 |

## Interpretation

A candidate can be invoked dynamically through dependency injection, framework registration, reflection, plugins, task queues, or external entrypoints. Review and focused tests are mandatory before deletion.
