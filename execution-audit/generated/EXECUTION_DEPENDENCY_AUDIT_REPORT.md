# Static Execution Dependency and Dead-Code Audit

> Repository evidence only. This report does not prove runtime reachability and performs no automatic deletion.

## Summary

- Python files parsed: **1838**
- FastAPI-style route handlers: **1048**
- Static function-call edges: **72408**
- Dead-code candidates: **614**
- Duplicate function groups: **58**
- Automatic deletions: **0**

## Highest-confidence dead-code candidates

| Owner | Symbol | Kind | File | Line |
|---|---|---|---|---:|
| `decision-service` | `_service_token_guard` | function | `services/decision-service/main.py` | 152 |
| `raster-service` | `_scene_band_mapping` | function | `services/raster-service/raster_main_compat_exports.py` | 92 |
| `raster-service` | `_bbox_from_geom` | function | `services/raster-service/raster_main_compat_exports.py` | 97 |
| `raster-service` | `_evict_field_layers` | function | `services/raster-service/raster_main_runtime.py` | 46 |
| `raster-service` | `_require_layer_tenant` | function | `services/raster-service/raster_main_runtime.py` | 89 |
| `raster-service` | `_require_layer_tenant_authorized` | function | `services/raster-service/raster_main_runtime.py` | 93 |
| `raster-service` | `_clean_cache` | function | `services/raster-service/test_cdse_empty_raster_not_cached.py` | 70 |
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
| `01e55555d0073910` | 2 |
| `0791c0d18167f804` | 5 |
| `10b234ebb823fb73` | 2 |
| `1652c685e5ed27fa` | 4 |
| `18a46eb263382a99` | 2 |
| `27213e0b8be4077c` | 3 |
| `2cab8792318c3811` | 2 |
| `2ed8e51be38a65b6` | 9 |
| `32d2f14c2fac8b6a` | 2 |
| `342931e6449b397f` | 2 |
| `3634c7c73fa8d02f` | 10 |
| `38f3e26a90604c6a` | 3 |
| `3bdaa4de02900ca1` | 2 |
| `3fa331af9f9461ea` | 9 |
| `406980d4b6534c4a` | 2 |
| `40b9faafbad5a23d` | 2 |
| `451e12ae0877302a` | 7 |
| `49b18910194fee42` | 2 |
| `4cb77c1b81129bbe` | 2 |
| `4d3489c6804536ee` | 2 |
| `558f76feaf3a04fa` | 3 |
| `5c83798b883cda7e` | 2 |
| `62a08c439a5d8220` | 2 |
| `69e415224b4d3b71` | 4 |
| `6a2cef3bc2a2519d` | 2 |
| `6dcb6ad9fc0cd5a9` | 2 |
| `6f642e211a717584` | 2 |
| `732840534ed80cbd` | 5 |
| `734027586cb4dbe9` | 2 |
| `7644d918a15bde1e` | 4 |
| `7753afc71b203ca1` | 2 |
| `785941ed0757008e` | 3 |
| `78b53236ba4d4e96` | 2 |
| `78da89549056e9b8` | 3 |
| `81bddc48412d7a77` | 2 |
| `828caff28d6627e7` | 2 |
| `8c325bfd965af37d` | 2 |
| `8e9f69a9666a9587` | 6 |
| `914184c711383573` | 5 |
| `9160c907b799819a` | 2 |
| `9975dc50917af5bc` | 2 |
| `9cd96fdce320f870` | 2 |
| `9e9d6bb7f5f44b29` | 2 |
| `9fcb13bf88a96d6a` | 2 |
| `a49b7c49171c8b3e` | 2 |
| `aa517cd1f9c74cf4` | 3 |
| `abea79905276671b` | 2 |
| `c866b724521642d7` | 2 |
| `c92554a020167fed` | 2 |
| `daa44aded5a16e85` | 2 |

## Interpretation

A candidate can be invoked dynamically through dependency injection, framework registration, reflection, plugins, task queues, or external entrypoints. Review and focused tests are mandatory before deletion.
