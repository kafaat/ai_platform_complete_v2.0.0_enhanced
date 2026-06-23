# 🧩 كتالوج الخدمات (Service Map)

> مُشتقّ من [`../../docker-compose.v9.yml`](../../docker-compose.v9.yml) (ملفّ الإنتاج القانونيّ) و
> [`../../nginx/nginx.v9.conf`](../../nginx/nginx.v9.conf). الوثيقة المعماريّة الكاملة:
> [`../../docs/SAHOOL_v9_Technical_Architecture.md`](../../docs/SAHOOL_v9_Technical_Architecture.md).
>
> **المنفذ الداخليّ** = المنفذ الذي تستمع عليه الخدمة داخل شبكة `sahool-internal` (لا منفذ المضيف).
> الخدمات بلا `build`/`main` ملفّها هو صورة جاهزة (image). الخدمات المُعلَّقة في الـcompose
> (`soil-service`/`video-processor`/`agriai-engine`) **غير مُدرَجة** (ليست منشورة).

## البنية التحتيّة (Infrastructure)

| الخدمة | المنفذ | الغرض | الصورة/الملفّ | متغيّرات مفتاحيّة | يعتمد على |
|---|---|---|---|---|---|
| `sahool-nginx` | 80/443 | بوّابة عكسيّة + TLS | `nginx:1.27-alpine` ([conf](../../nginx/nginx.v9.conf)) | `DOMAIN`, `SAHOOL_AGENT_TOKEN` | auth, supervisor, guardrails, vegetation, indicators, weather, market-mcp, odoo-bridge, local-ai-rag (healthy) |
| `sahool-postgres` | 5432 | PostgreSQL + PostGIS | `postgis/postgis:15-3.4` | `POSTGRES_DB/USER/PASSWORD` | — |
| `sahool-redis` | 6379 | كاش/جلسات (requirepass) | `redis:7-alpine` | `REDIS_PASSWORD` | — |
| `sahool-nats` | 4222 (8222 مراقبة) | NATS JetStream (أحداث) | `nats:2-alpine` ([conf](../../nats/nats.conf)) | `nats.conf` | — |
| `sahool-minio` | 9000/9001 | تخزين كائنات S3 | `minio/minio` | `MINIO_ROOT_USER/PASSWORD` | — |
| `sahool-qdrant` | 6333 | متّجهات RAG (distroless، بلا healthcheck) | `qdrant/qdrant:v1.17.1` | `QDRANT__SERVICE__API_KEY` | — |
| `sahool-ollama` | 11434 | استدلال LLM/embeddings محليّ | `ollama/ollama:0.3.14` | (GPU اختياريّ) | — |
| `sahool-migrate` | — (one-shot) | تطبيق الترحيلات + دور `sahool_app` المقيّد | `postgis/postgis:15-3.4` ([apply](../../migrations/apply_in_compose.sh)) | `APP_DB_ROLE`, `JOBS_DB_ROLE` | postgres (healthy) |

## التطبيق الأساسيّ (Core App)

| الخدمة | المنفذ | الغرض | الملفّ الرئيس | متغيّرات مفتاحيّة | يعتمد على |
|---|---|---|---|---|---|
| `sahool-auth` | 8000 | المصادقة/الهويّة (JWT/MFA) | [`services/auth/main.py`](../../services/auth/main.py) | `JWT_SECRET`, `DATABASE_URL`, `ADMIN_PASSWORD` | postgres, redis, migrate |
| `sahool-platform` | 8000 | المنطق الأساسيّ (`/api/v1/*`) + أعلام ميزات | [`services/sahool-platform/api/main.py`](../../services/sahool-platform/api/main.py) | `SAHOOL_JWT_SECRET`, `JOBS_DATABASE_URL`, `RASTER_SERVICE_URL`, `FEATURE_*` | postgres, redis, migrate, field-segmentation |
| `sahool-supervisor-agent` | 8000 | وكيل التنسيق (يستدعي MCP) | [`services/supervisor-agent/main.py`](../../services/supervisor-agent/main.py) | `MCP_*_URL`, `SAHOOL_AGENT_TOKEN` | auth (healthy) |
| `sahool-guardrails-engine` | 8000 | حَوكمة/تحقّق (fail-closed) | [`services/guardrails-engine/main.py`](../../services/guardrails-engine/main.py) | `SAHOOL_AGENT_TOKEN`, `JWT_SECRET` | postgres, redis |

## خوادم MCP (نفس [`Dockerfile`](../../services/mcp_servers/Dockerfile))

| الخدمة | المنفذ | الغرض | متغيّرات مفتاحيّة | يعتمد على |
|---|---|---|---|---|
| `sahool-sentinel-hub-mcp` | 8000 | MCP صور Sentinel Hub | `SH_CLIENT_ID/SECRET` | — |
| `sahool-weather-mcp` | 8000 | MCP الطقس | `JWT_SECRET` | — |
| `sahool-wofost-mcp` | 8000 | MCP نموذج المحصول WOFOST | `JWT_SECRET` | — |
| `sahool-market-mcp` | 8000 | MCP السوق (عبر جسر ERP) | `ODOO_BRIDGE_URL` | postgres |

## التحليل والصور والطقس (Analytics / Imagery / Weather)

| الخدمة | المنفذ | الغرض | الملفّ الرئيس | متغيّرات مفتاحيّة | يعتمد على |
|---|---|---|---|---|---|
| `sahool-vegetation-analysis` | 8000 | تحليل الغطاء النباتيّ | [`services/vegetation-analysis-service/`](../../services/vegetation-analysis-service/) | `SH_CLIENT_ID/SECRET`, `CDSE_*` | nats (healthy) |
| `sahool-raster-service` | **8001** | صور Sentinel-2/1 عبر Element84 STAC | [`services/raster-service/main.py`](../../services/raster-service/main.py) | `EARTH_SEARCH_URL`, `TITILER_URL`, `STAC_*` | — |
| `sahool-titiler` | 8000 | خادم بلاطات COG ديناميكيّ | `ghcr.io/developmentseed/titiler:0.18.6` | `TITILER_API_CORS_ORIGINS` | — |
| `sahool-indicators-service` | 8000 | مؤشّرات + `/metrics` | [`services/indicators-service/`](../../services/indicators-service/) | `DATABASE_URL`, `NATS_URL` | postgres, redis, nats |
| `sahool-weather-service` | 8000 | خدمة الطقس | [`services/weather-service/`](../../services/weather-service/) | `NATS_URL` | nats (healthy) |
| `sahool-weather-polygon-worker` | — (عامل) | ربط تنبّؤ الطقس بالحقول مكانيّاً | [`services/weather-polygon-worker/src/main.py`](../../services/weather-polygon-worker/src/main.py) | `JOBS_DATABASE_URL` (BYPASSRLS) | postgres, nats, migrate |
| `sahool-weather-signal-engine` | — (عامل) | توليد إشارات الطقس مجدوَلاً | [`services/weather-signal-engine/`](../../services/weather-signal-engine/) | `JOBS_DATABASE_URL` | postgres, migrate |

## الحافة والتحكّم والتقطيع (Edge / Actuation / Segmentation)

| الخدمة | المنفذ | الغرض | الملفّ الرئيس | ملاحظة |
|---|---|---|---|---|
| `sahool-actuator-service` | 8000 | أوامر المُشغّلات (صمّامات/مضخّات) | [`services/actuator-service/`](../../services/actuator-service/) | يتّصل بـMQTT `sahool-fastbee:1883` |
| `sahool-fastbee` | 1883 | وسيط MQTT خفيف | `eclipse-mosquitto:2` | يُصلِح M3 (الوسيط المفقود سابقاً) |
| `sahool-edge` | 8100 | استدلال الحافة (arm64/RPi) | [`services/edge-inference/Dockerfile.arm64`](../../services/edge-inference/Dockerfile.arm64) | OFFLINE_MODE |
| `sahool-field-segmentation` | 8000 | تقطيع الحقل (يدويّ حقيقيّ؛ auto/hybrid 503 صادق) | [`services/field-segmentation/main.py`](../../services/field-segmentation/main.py) | يفعّله SAM2 |
| `sahool-sam2-inference` | 8080 | استدلال SAM2 على GPU (**opt-in** `profile=gpu`) | [`services/sam2-inference/main.py`](../../services/sam2-inference/main.py) | 503 صادق بدون نموذج |

## RAG والتكامل والبوتات (RAG / Integrations / Bots)

| الخدمة | المنفذ | الغرض | الملفّ الرئيس | ملاحظة |
|---|---|---|---|---|
| `sahool-local-ai-rag` | 8000 | RAG محليّ (Qdrant + Ollama) | [`services/local-ai-rag/`](../../services/local-ai-rag/) | `EMBEDDING_URL`/`LLM_URL` → ollama |
| `sahool-qdrant-seed` | — (one-shot) | بذر متّجهات Qdrant | [`services/qdrant-seed/`](../../services/qdrant-seed/) | `restart: "no"` |
| `sahool-odoo-bridge` | 8126 | جسر ERP (erpnext/odoo/none) | [`services/odoo-bridge/`](../../services/odoo-bridge/) | `ERP_PROVIDER` |
| `sahool-odoo` | 8069 | Odoo ERP (`profile=odoo` فقط) | `odoo:17.0` ([init](../../scripts/odoo-init.sh)) | قاعدة منفصلة `sahool_erp` |
| `sahool-telegram-bot` | — (polling) | بوت تيليجرام | [`bots/telegram/`](../../bots/telegram/) | `TELEGRAM_BOT_TOKEN` |
| `sahool-notification-agent` | 8123 | الإشعارات + WebSocket `/ws/` | [`agents/notification/agent.py`](../../agents/notification/agent.py) | يشترك بمواضيع NATS |
| `sahool-frontend` | 8080 | الواجهة (React/Vite) | [`frontend/Dockerfile`](../../frontend/Dockerfile) | `VITE_API_URL` |

## الرصد (Observability)

| الخدمة | المنفذ | الغرض | الصورة |
|---|---|---|---|
| `sahool-prometheus` | 9090 | جمع المقاييس | `prom/prometheus:v2.53.0` |
| `sahool-alertmanager` | 9093 | توجيه الإنذارات | `prom/alertmanager:v0.27.0` |
| `sahool-grafana` | 3000 | لوحات القيادة | `grafana/grafana:10.4.5` |
| `sahool-jaeger` | 16686 | التتبّع الموزّع | `jaegertracing/all-in-one:1.57` |

---

## 🌐 خريطة بوّابة nginx (route → upstream)

مُشتقّة من [`../../nginx/nginx.v9.conf`](../../nginx/nginx.v9.conf). الـ`upstream`ات معرّفة عند
`nginx.v9.conf:59-75`، والمسارات عند `:117-290`. ملاحظة: `edge`/`soil` لا يملكان upstream مباشراً —
يُمرَّران عبر المنصّة (`platform_backend`) التي تستدعيهما داخليّاً عبر `service_proxy`.

| المسار (location) | الوجهة (proxy_pass) | الخدمة | السطر |
|---|---|---|---|
| `= /_auth_verify` | `auth_backend/auth/verify` | auth | `:133` |
| `/auth/` | `auth_backend` | auth | `:144` |
| `/api/v1/` | `platform_backend/api/v1/` | platform | `:159` |
| `/api/indicators/` | `platform_backend/api/v1/indicators/` | platform | `:172` |
| `/api/vegetation/` | `vegetation_backend/` | vegetation-analysis | `:177` |
| `/api/raster/` | `raster_backend/` (8001) | raster-service | `:187` |
| `/api/edge/` | `platform_backend/api/edge/` | platform → edge | `:203` |
| `/api/weather/` | `platform_backend/api/v1/weather/` | platform | `:210` |
| `/api/soil/` | `platform_backend/api/soil/` | platform → soil | `:218` |
| `/api/segmentation/` | `platform_backend/api/segmentation/` | platform → field-segmentation | `:226` |
| `= /api/agent/health` | `supervisor_backend/health` | supervisor-agent | `:238` |
| `/api/agent/` | `supervisor_backend/agent/` | supervisor-agent | `:243` |
| `/api/guardrails/` | `guardrails_backend/` | guardrails-engine | `:249` |
| `/ws/` | `notification_ws/ws/` (8123) | notification-agent | `:254` |
| `/metrics` | `indicators_backend/metrics` | indicators-service | `:270` |
| `/` (+ `@spa_fallback`) | `frontend_backend/` (8080) | frontend | `:283` |
