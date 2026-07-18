# خريطة بيئات التفعيل الحيّة (Live Activation Environments)

> مسح برمجيّ شامل READ-ONLY للشجرة كاملة: كلّ ما يحتاج **بيئة تفعيل حيّة** (بنية تحتيّة أو
> قلب راية أو سرّ أو تزويد خارجيّ) ليعمل فعلاً في الإنتاج — بخلاف الكود المُعتمَد المُختبَر
> وحدويّاً. مُصنَّف حسب قرار **A/B/C** المعماريّ المعتمَد.
>
> **A** — تفعيل آليّ مسموح: ميزة قابلة للتعطيل/الفحص دون أثر ماديّ (مزوّد بيانات/طبقة قراءة/معالجة
> داخليّة). قلب راية أو تزويد اعتماد ⇒ تُفعَّل بأمان.
> **B** — شهادة نشر لا تفعيل runtime: البوّابة **تستهلك دليلها** (لا تعيد تنفيذه) — ترحيلات ترقية،
> شهادة تزامن، اختبارات حيّة، failover.
> **C** — لا تفعيل آليّ كامل: أثر ماديّ/ماليّ. العقد الإلزاميّ
> `technical_ready ∧ operator_approved ∧ safety_interlock_ready`؛ لا يمكن لبوّابة ذاتيّة تحويل
> `technical_ready` وحده إلى `enabled`.
>
> **قاعدة عدم ازدواج الجاهزيّة:** بوّابة التفعيل لا تعيد إنتاج فحوص يملكها مكوّن آخر؛ تستهلك دليلاً
> يحمل `producer · check_name · observed_at · valid_until · result · provenance/version · environment_id`.
>
> المصدر: مسح 2026-07-18 (4 عوامل متوازية). التصنيف اجتهاديّ قابل للمراجعة. `file:line` مرجعيّة.

---

## Category A — تفعيل آليّ مسموح (قراءة/بيانات/داخليّ، لا أثر ماديّ)

### A1 — رايات نقاط النهاية (`FEATURE_*`) — قلب الراية يكشف المسار (404 حتى ذلك)
مُسجَّلة مركزيّاً في `services/sahool-platform/api/feature_registry.py:20-47` (unset/فارغ ⇒ OFF ⇒ 404). compose يوصّلها `:-0`.

| الراية | الموقع | القدرة |
|---|---|---|
| FEATURE_PORTFOLIO_COMMAND | routers/portfolio_command.py:33 | مركز أوامر المحفظة |
| FEATURE_DEVICE_TWIN | routers/device_twin.py:34 | توأم رقميّ للجهاز (يحتاج telemetry) |
| FEATURE_DELTA_SYNC | routers/sync.py:47 | مزامنة دلتا للعملاء دون اتصال |
| FEATURE_NATURAL_LANGUAGE_GIS | routers/nl_gis.py:41 | NL→GIS (قد يحتاج LLM/RAG) |
| FEATURE_DECISION_STUDIO | routers/decision_explain.py:42 | استوديو تفسير القرار |
| FEATURE_OPERATIONS_WALL | routers/operations.py:36 | جدار العمليّات الحيّ |
| FEATURE_REPLAY_MAP | routers/agronomic_replay.py:32 | خريطة إعادة الموسم |
| FEATURE_EVIDENCE_MAP | routers/evidence_map.py:33 | خريطة طبقات الدليل |
| FEATURE_LEARNING_DASHBOARD | routers/learning_summary.py:37 | لوحة حلقة التعلّم |
| FEATURE_DECISION_CONFIDENCE | routers/decision_confidence.py:38 | ثقة القرار الموحّدة |
| FEATURE_UNIFIED_LINEAGE | routers/execution_lineage.py:33 | نَسَب التنفيذ |
| FEATURE_GIS_KERNEL | routers/gis_kernel.py:48 | عمليّات GIS منخفضة (تحتاج PostGIS) |
| FEATURE_IRRIGATION_NETWORK | routers/irrigation_network.py:26 | توأم شبكة الريّ |
| FEATURE_EXECUTION_FEEDBACK | routers/execution_feedback.py:31 | حلقة تغذية التنفيذ |
| FEATURE_FARM_OPERATIONS_LEDGER | routers/farm_operations_ledger.py:820 | دفتر عمليّات المزرعة (⚠️ أثر ماليّ — راجع C) |

### A2 — اعتمادات مزوّدين/بنية بيانات (fail-closed حتى التزويد)
| المزوّد | الكود | file:line | العَرَض عند الغياب |
|---|---|---|---|
| CDSE/Copernicus (S2 L2A) | `CDSE_CLIENT_ID/SECRET` | raster-service/cdse_client.py:94-99؛ .env.example:34-40 | ليس fail-hard: يسقط لـElement84؛ backfill بـcdse بلا اعتماد ⇒ 503 مُهيكَل |
| Sentinel Hub (تجاريّ, MCP) | `SH_CLIENT_ID/SECRET/INSTANCE_ID` | mcp_servers/sentinel_hub_server.py:33-36,147-160 | 401 → أدوات imagery معطّلة |
| Element84 Earth Search | لا مفتاح (شبكة فقط) | raster-service/stac_search.py:19,233-267 | فشل STAC كامل ⇒ 503 صادق |
| Open-Meteo (طقس أساسيّ) | لا مفتاح | weather-service/open_meteo.py:138,453-473 | breaker يفتح ⇒ RuntimeError؛ `/readyz` degraded |
| MET.no (طقس ثانٍ) | `METNO_USER_AGENT` | .env.example:166-170 | UA عام ⇒ رفض؛ احتياط اتّجاه الريح يغيب |
| S3/MinIO (تخزين COG) | `S3_BUCKET/ENDPOINT/ACCESS_KEY/SECRET_KEY` | raster-service/object_store.py:23-75,109-151 | بلا مفاتيح ⇒ fail-closed إلّا `S3_ALLOW_FILE_FALLBACK=1` ⇒ `file://` غير قابل للخدمة |
| MQTT (FastBee) | `MQTT_BROKER_URL` | actuator-service/actuator_runtime.py:22,45-50 | فارغ ⇒ MODE disabled (⚠️ أثر ماديّ — راجع C) |
| NATS | `NATS_URL` | agents/base_agent.py:40-41؛ .env.example:107 | نشر vegetation best-effort؛ العمّال يفقدون fan-out |
| ERPNext/Odoo | `ERPNEXT_API_KEY/SECRET` أو `ODOO_*` | odoo-bridge/erp_provider.py:398-436 | يهبط لـ`none` بصدق؛ `/health` erp_enabled:false |
| Qdrant/Ollama | `QDRANT_API_KEY`؛ Ollama URL | local-ai-rag/main.py:269,287,416,509 | RAG/KG غير جاهز |
| Redis | `REDIS_PASSWORD` | auth session/reset/mfa | refresh/reset/email/mfa يفشل مُغلَقاً |
| Telegram | `TELEGRAM_BOT_TOKEN` | bots/telegram/main.py | البوت لا يتّصل |
| Mapbox/MapTiler (واجهة) | `VITE_MAPBOX_TOKEN` | .env.example:75-78 | اختياريّ — يسقط لـEsri الخريطة لا تنكسر |

### A3 — GPU (استدلال — أثر بيانات، 503 صادق)
| القدرة | البوّابة | file:line | الاحتياط |
|---|---|---|---|
| SAM2 حدود الحقل | CUDA + `SAM2_CHECKPOINT` | sam2-inference/sam2_runtime.py:55,110-151؛ compose `--profile gpu` v9.gpu.yml:21 | بلا GPU ⇒ `/predict` 503؛ `/readyz` model_loaded:false |
| بوّابة التجزئة | `SEGMENTATION_REQUIRE_MODEL` | scripts/e2e/segmentation_platform_live_gate.py:82-86 | بلا نموذج ⇒ احتياط يدويّ بلا تلفيق |
| XTTS صوتيّ | `XTTS_ENABLE`/`TTS_GPU_PROVIDER=xtts` + مكتبة TTS | tts-service/providers.py:134-163 | غير متاح ⇒ edge-tts (CPU) |
| Piper صوتيّ | `PIPER_VOICE_PATH` | tts-service/providers.py:100-127 | ⇒ edge-tts |

### A4 — رايات إسقاط/معالجة داخليّة (قلب الراية يكفي)
`services/sahool-platform/api/field_state_projection.py`: FEATURE_WATER_STRESS_ESCALATION:38 · FEATURE_CANONICAL_ETC_DUAL:42 · FEATURE_CANONICAL_SALINITY:47 · APPLY_NDVI_THRESHOLDS:51 · agriai `AGRIAI_PRODUCTION_MODE` wofost_adapter.py:292 · vegetation `VEGETATION_EVIDENCE_PUSH_ENABLED` vegetation_runtime.py:124 (يحتاج decision-service).

### A5 — أسرار بوّابة الخدمات (fail-closed حتى الضبط — شرط لا ميزة)
| السرّ | الخدمات | file:line | العَرَض |
|---|---|---|---|
| **JWT_SECRET** (≥32) | auth · actuator · guardrails · vegetation · supervisor · local-ai-rag · odoo · market MCP · tts | .env.example:17؛ shared/oauth_middleware.py:45-49 | 503/500 «الخدمة معطّلة بأمان» |
| **MFA_SECRET_ENCRYPTION_KEY** (Fernet) | auth MFA | auth/mfa_crypto.py:9,65,103-128 | إعداد MFA يفشل؛ يحجب `REQUIRE_MFA_ROLES` |
| **SAHOOL_AGENT_TOKEN** | SAM2 · soil · agriai · local-ai-rag · raster upload · guardrails /validate | sam2_runtime.py:94؛ guardrails/main.py:383 | 503 على ingest/upload/validate |

---

## Category B — شهادة نشر (البوّابة تستهلك دليلها، لا تعيد تنفيذه)

### B1 — اختبارات تحتاج بنية حيّة (تتخطّى/تفشل مُغلَقة تحت راية)
البوّابة المشتركة `tests_v9/conftest.py:35,109-127` (فشل الاتصال ⇒ skip). أمثلة تمثيليّة:
- **IRR-F01 الحيّ** (PG+PostGIS + دور RLS مقيّد): `tests_v9/test_irr_f01_reservation_live_pg.py:41,43` (يفشل عند `IRR_F01_CERTIFICATION_REQUIRED=1`) · `test_irr_f01_upgrade_gate_u1_pg.py:29-30`.
- **RLS**: `test_rls_isolation*.py` · `test_rls_write_isolation_integration.py:17` · `test_rls_role_hardening_v66.py` · `test_field_management_pg_isolation_integration.py:27,42` (دور NOBYPASSRLS).
- **سلسلة القرار/التنفيذ** (PG): `test_dispatch_hardening_ledger_integration.py` · `test_dispatch_decisions_integration.py` · `test_actuation_killswitch_v29_5_op.py` · `test_irrigation_runs_v29_5_op.py`.
- **decision-service SoR suite** (PG + `migration_runner --apply` + `DECISION_SERVICE_SOR_ENABLED=true`): كامل `services/decision-service/tests/*` (WX-10.7…WX-12.3، AC-1/6.1، no-leakage، Gate-B inbox).
- **Redis**: `test_auth_session_revocation.py:102` · `weather-service/tests/test_weather_redis_live_optional.py`.
- **الحزمة الكاملة (خدمات تعمل)**: `test_end_to_end.py` · `test_smoke_e2e.py` · `test_services_functional.py` · `test_mcp_functional.py`.

### B2 — وظائف CI ترفع بنية حقيقيّة (تنتج الدليل)
| Workflow : job | يرفع | يشهد |
|---|---|---|
| ci.yml : **Integration Tests** :535 | postgis:15-3.4 :5433 + redis :6380؛ دور `sahool_app_test` NOBYPASSRLS :598-624 | `pytest -m integration` + IRR-F01 Gate A/B1 (`IRR_F01_CERTIFICATION_REQUIRED=1`) + Gate U1 ترقية :631-649 |
| ci.yml : **Decision Service Tests** :651 | postgres:15 :5434؛ `migration_runner --apply` 001→027 | mirror-off + SoR-on: WX-10.7→11.6، **Gate-B reservation inbox :748-752**، WX-12، AC-1/6.1، no-leakage |
| wx12-runtime-certification.yml : postgres :19 | postgis:16-3.4 :5432 | كامل decision-service suite على PG حيّ |
| production-certification-blockers.yml : P-CERT-3 :43 | Redis خارجيّ (`WEATHER_REDIS_INTEGRATION_URL`) | شهادة redis الحيّة للطقس |

### B3 — خطوات نشر يطبّقها المشغّل (ليست startup)
- `services/decision-service/migration_runner.py --apply` (+`--check`) — مخطّط SoR؛ Runbook `docs/architecture/DECISION_SERVICE_SOR_MIGRATION.md:41`.
- `backfill.py --verify-counts/--verify-review` — تكافؤ + quarantine قبل القلب (غير الفارغ يحجب).
- `cutover.py` + `/v1/cutover/readiness` — نموذج جاهزيّة حتميّ (٦ جداول SoR؛ راية واحدة لا تكفي).
- `production_promotion.py` — يتطلّب `DECISION_SERVICE_PRODUCTION_PROMOTION_APPROVED` + `_ALLOW_LIVE` + `SOR_ENABLED=true`.
- `migrations/MANIFEST.txt` عبر `psql` (حاوية `sahool-migrate` قبل العمّال).
- `scripts/production_validation_gate.sh` · `scripts/security/rls_runtime_gate.py` (دور NOBYPASSRLS).
- `scripts/irr_f01/upgrade_gate_u1.sh` — ترقية v194→v195/v196.

---

## Category C — أثر ماديّ/ماليّ: لا تفعيل آليّ كامل (`technical ∧ operator ∧ safety`)

### C1 — سلسلة تنفيذ decision-service SoR (بوّابة التنفيذ الفيزيائيّ)
كلّها fail-closed خلف `sor_enabled()` (main.py:80,386). تُفعَّل فقط بقلب SoR (Postgres + راية) — وهي **مسبوقة بموافقة WX-10** (decision_record approved + plan planned + authorization authorized):
- `/v1/execution-plans/{id}/authorize-dispatch` main.py:1001,1032-1035 — **تصريح الإرسال**.
- `/v1/dispatch-authorizations/{id}/execute` main.py:1069,1097-1100 — **التنفيذ/التشغيل**.
- `/v1/reservation-dispatch-intents` main.py:1128,1139-1142 — صندوق قصد الحجز (تسليم لا إيفاء — IRR-F01 Slice 1).
- `/v1/execution-requests/{id}/claim|receipt|verify-outcome` main.py:1222-1329.
- BFF منصّة موازية fail-closed: `routers/decision_review.py` (apply:139, dispatch-auth:346, execution:411).

### C2 — actuator-service + عمّال الأثر الفيزيائيّ (opt-in افتراضاً)
| البند | file:line | البوّابة |
|---|---|---|
| `/command` تحكّم الجهاز | actuator_runtime.py:476 (JWT), 507-525 (ownership), 288 (mirror 503) | JWT + Postgres + SoR up |
| `FEATURE_DISPATCH_ACTUATOR` | actuator_runtime.py:58 | OFF افتراضاً — جسر القرار→actuator |
| `FEATURE_MANUAL_ACTUATOR_COMMANDS` / `_AUTOMATION_RULES_ACTUATION` | actuator_runtime.py:56-57 | OFF افتراضاً |
| `PHYSICAL_ACTUATION_ENABLED` | phase_runtime_workers.py:299؛ compose v9.yml:2136 | OFF — عامل actuator-dispatch |
| خدمات compose opt-in | docker-compose.v9.yml:2113-2156 (actuator-dispatch-worker), 1922-1965 (outbox-worker) | جميعها `PHYSICAL_ACTUATION_ENABLED=false` |
| MQTT broker | mosquitto v9.yml:1299-1307 | لازم للتسليم الفعليّ |

### C3 — أثر ماليّ/تنفيذ آليّ
- `WATER_DEFICIT_AUTO_EXECUTION_ENABLED` water_decision_bridge.py:65 — **تنفيذ آليّ لعجز الماء** (OFF).
- دفتر العمليّات: `routers/farm_operations_ledger.py:218,535,643` · دفتر الماء `water_ledger.py:97-242` — كتابات ماليّة (تحتاج Postgres؛ أثر ماليّ).
- market MCP: `mcp_servers/market_server.py:60,215,733` — سوق (أثر ماليّ).

### C4 — تفعيل حوكميّ (دورة حياة النماذج — C-adjacent)
promotion/activation/rollback في decision-service (main.py:1477-1708) — تغيير مُفعَّل مُحكوم؛ يمرّ عبر SoR + موافقة، لا يُقلَب ذاتيّاً.

---

## عناقيد الاعتماد (dependency → ما يُفتَح)
- **Postgres SoR flip** (`DECISION_SERVICE_SOR_ENABLED=true`+`DATABASE_URL`): أكبر عنقود fail-closed (~42 بوّابة decision-service + BFF)؛ الوحيد الحاكم للإرسال الفيزيائيّ. **[B للشهادة · C للتفعيل]**
- **JWT_SECRET / SAHOOL_AGENT_TOKEN**: أسرار بوّابة عبر ~10 خدمات. **[A5]**
- **SAM2 GPU + أوزان**: حدود الحقل. **[A3]**
- **S3/MinIO · CDSE/Element84 · Open-Meteo · Redis · Qdrant/Ollama · NATS · MQTT**: مزوّدون/بنية. **[A2 عدا MQTT ⇒ C]**
- **FCM_SERVER_KEY** (غائب عن .env.example) — Mobile push (agents/notification/agent.py:169-249). **[A/موبايل]**
- **Flutter/Dart SDK** — غير موجود في البيئة؛ push/analyze/test مؤجَّلة. **[A/موبايل مؤجَّل]**
- **DEM إنتاجيّ** (`FIELD_DEM_PATH`) — تضاريس 3D. **[A/بيانات]**

## رايات default-ON (خارج النطاق — مُفعَّلة ما لم تُطفَأ)
TILE_CACHE_ENABLED · SOIL_PROJECTION_WORKER_ENABLED · ENABLE_LIVE_GUARDRAILS · METNO_WIND_FALLBACK_ENABLED · VEGETATION_PREFER_RASTER/CANONICAL · RASTER_ASYNC_BACKFILL/CACHE_INVALIDATION · CDSE_ENABLED · STAC_FALLBACK_ENABLED · REQUIRE_MFA_ROLES=admin · COLLECTOR_OTLP_ENABLED.

## رايات auto-ON في الإنتاج (dormant في dev فقط)
VEGETATION_REAL_ONLY · FEATURE_SENTINEL_DB_FIELDS · AGRIAI_STRICT_CONTEXT · DECISION_REQUIRE_SOIL_PROFILE (`SAHOOL_ENV=production`).

---

**الخلاصة:** غالب الشجرة **fail-closed صادق** لا fail-open: غياب اعتماد ⇒ 503/424/degraded لا بيانات مُلفّقة.
البوّابات الفيزيائيّة/الماليّة (C) محصورة في: سلسلة decision-service SoR، `actuator /command` وعمّاله،
تنفيذ عجز الماء الآليّ، والدفاتر الماليّة — وكلّها تتطلّب `operator_approved` + `safety_interlock` فوق
`technical_ready`، تماشياً مع ACTIVATION-GATE قرار A/B/C.
