# SAHOOL v9.1 — Unified Production Setup Guide
> **التاريخ:** 2026-05-19  
> **الحزم المدمجة:** Edge-Ready + AI/GIS + Odoo Bridge + Market + AgriAI Engine  
> **الخدمات:** 20+ | **الطبقات:** 8 | **الأمر الواحد:** `./scripts/setup_unified.sh`

---

## 🎯 ما هو الإعداد الموحد (Unified Setup)؟

بدلاً من 5 حزم منفصلة، هذا الإعداد يجمع **كل شيء** في `docker-compose.unified.yml` واحد:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: Gateway & Frontend                                                │
│  ├─ nginx (443) — Reverse Proxy + SSL                                       │
│  └─ frontend — Vue/React SPA (placeholder)                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 2: Core Services                                                     │
│  ├─ auth-service (:8120) — JWT Auth + Users                                 │
│  ├─ supervisor-agent (:8096) — AI Orchestrator (MCP Client)                   │
│  └─ guardrails (:8097) — Safety + Approval Tiers                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 3: MCP Data & AI Servers                                             │
│  ├─ sentinel-hub-mcp (:8091) — Satellite NDVI/S2                              │
│  ├─ weather-mcp (:8092) — Open-Meteo / OpenWeather                          │
│  ├─ wofost-mcp (:8093) — Crop Growth Model                                   │
│  └─ market-mcp (:8094) — B2B Marketplace + Procurement                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 4: Edge & IoT                                                         │
│  ├─ edge-inference (:8100) — YOLO/ONNX Pest Detection                        │
│  ├─ video-processor (:8110) — RTSP/FLV/WebRTC Frame Analysis               │
│  ├─ actuator-service (:8111) — Scene Linkage (MQTT Commands)                  │
│  ├─ fastbee (:1883+8081) — MQTT Broker + Device Management                 │
│  └─ zlmediakit (:8082+554) — Video Gateway (WebRTC/FLV/HLS)                │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 5: AI & RAG (Local LLM)                                              │
│  ├─ ollama (:11434) — Qwen3 / Llama / Mistral                               │
│  ├─ local-ai-rag (:8125) — Qdrant + LangChain RAG                           │
│  └─ qdrant (:6333) — Vector Database                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 6: AgriAI Engine (Unified Intelligence)                              │
│  └─ agriai-engine (:8127) — 5 Models: Soil + Crops + Irrigation + Pest + Yield │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 7: ERP & Business                                                    │
│  └─ odoo-bridge (:8126) — Bidirectional Odoo ERP Sync                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 8: Bots & Notifications                                              │
│  └─ telegram-bot — Alerts + AI Advisor Chat                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE                                                              │
│  ├─ postgis (:5432) — PostgreSQL + PostGIS + Timescale (optional)             │
│  ├─ redis (:6379) — Cache + Sessions + Rate Limiting                        │
│  ├─ nats (:4222) — Event Bus + JetStream                                   │
│  └─ minio (:9000+9001) — Object Storage (S3-compatible)                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 التشغيل السريع (One Command)

```bash
# 1. استخرج الحزمة
unzip sahool-v91-unified.zip
cd sahool-v91-unified

# 2. شغّل (يولد .env تلقائياً)
chmod +x scripts/setup_unified.sh
./scripts/setup_unified.sh

# 3. انتظر 3-5 دقائق حتى تكتمل جميع الطبقات

# 4. افتح المتصفح
https://localhost          # Frontend
https://localhost/api/     # API Gateway
```

---

## ⚙️ التكوين اليدوي (قبل الإنتاج)

### 1. نسخ ملف البيئة

```bash
cp .env.unified.example .env
nano .env  # عدّل كل القيم المطلوبة
```

### 2. القيم الإلزامية

| المتغير | المصدر | الوصف |
|---------|--------|-------|
| `SH_CLIENT_ID` | [Sentinel Hub](https://docs.sentinel-hub.com) | بيانات الأقمار الصناعية |
| `SH_CLIENT_SECRET` | Sentinel Hub | — |
| `TELEGRAM_BOT_TOKEN` | [BotFather](https://t.me/botfather) | بوت Telegram |
| `MAPBOX_TOKEN` | [Mapbox](https://account.mapbox.com) | الخرائط |
| `ODOO_API_KEY` | Odoo Settings | تكامل ERP |
| `POSTGRES_PASSWORD` | تولد تلقائياً | قاعدة البيانات |
| `JWT_SECRET` | تولد تلقائياً | توكنات المستخدمين |

### 3. SSL للإنتاج

```bash
# Let's Encrypt (إنتاج)
sudo certbot certonly --standalone -d your-domain.com
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem nginx/ssl/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem nginx/ssl/

# أو self-signed (تطوير فقط — يولد تلقائياً)
```

---

## 📡 نقاط النهاية (Endpoints)

### API Gateway (عبر Nginx)

| المسار | الخدمة | الدليل |
|--------|--------|--------|
| `/auth/` | auth-service | تسجيل دخول + JWT |
| `/api/agent/` | supervisor-agent | الوكيل الذكي |
| `/api/sentinel/` | sentinel-hub-mcp | صور الأقمار |
| `/api/weather/` | weather-mcp | الطقس |
| `/api/wofost/` | wofost-mcp | نمو المحصول |
| `/api/market/` | market-mcp | السوق + المشتريات |
| `/api/edge/` | edge-inference | كشف الآفات |
| `/api/video/` | video-processor | كاميرات RTSP |
| `/api/actuator/` | actuator-service | التحكم الآلي |
| `/api/rag/` | local-ai-rag | استشاري ذكاء اصطناعي |
| `/api/agriai/` | agriai-engine | 5 نماذج زراعية |
| `/api/odoo/` | odoo-bridge | تكامل ERP |
| `/live/` | zlmediakit | بث مباشر |
| `/fastbee/` | fastbee | إدارة الأجهزة |

### مباشرة (للتطوير)

| المنفذ | الخدمة |
|--------|--------|
| 8120 | Auth |
| 8096 | Supervisor Agent |
| 8125 | Local AI RAG |
| 8126 | Odoo Bridge |
| 8127 | AgriAI Engine |
| 9001 | MinIO Console |
| 11434 | Ollama API |
| 1883 | MQTT (FastBee) |

---

## 🗄️ قاعدة البيانات (PostGIS)

### الجداول المدمجة (من 5 migrations)

| Migration | الجداول | الغرض |
|-----------|---------|-------|
| `v9_new_tables.sql` | users, fields, crops, inventory_stock, satellite_data | البنية الأساسية |
| `v9_automation.sql` | automation_rules, device_commands_log, thing_models, iot_devices, procurement_orders, suppliers, video_streams | التحكم الآلي + IoT + مشتريات |
| `v9_market.sql` | market_products, market_suppliers, market_price_history, market_procurement_orders, market_sales_listings | السوق + الأسعار |
| `v9_odoo_bridge.sql` | odoo_sync_state, odoo_sync_log, field_cost_ledger, crop_batches, workflow_instances | ERP + تكاليف + Workflow |
| `v9_agriai.sql` | agriai_soil_analyses, agriai_crop_recommendations, agriai_irrigation_schedules, agriai_pest_alerts, agriai_yield_predictions | 5 نماذج AgriAI |

**الإجمالي:** 25+ جدول — كلها محمية بـ RLS (Row Level Security).

---

## 🔄 سير العمل الموصى به (Workflow)

### السيناريو: مزرعة قمح جديدة

```bash
# 1. تحليل التربة
curl -X POST https://localhost/api/agriai/analyze-soil   -d '{"field_id":"field_new","soil_data":{"ph":6.5,...}}'
# ← score: 72, grade: B — توصيات: أضف فوسفات

# 2. اقتراح محاصيل
curl -X POST https://localhost/api/agriai/recommend-crops   -d '{"field_id":"field_new","location":{"lat":15.35,"lng":44.21}}'
# ← wheat: 92.5%, barley: 88.3%

# 3. جدولة ري
curl -X POST https://localhost/api/agriai/schedule-irrigation   -d '{"field_id":"field_new","crop_type":"wheat","soil_moisture_pct":25,"auto_create_rules":true}'
# ← 3 events, 1575 m³ — rules created in automation_rules

# 4. طلب أسمدة
curl -X POST https://localhost/api/market/procurement   -d '{"items":[{"product_name":"Urea 46%","quantity":2000,"unit":"kg"}]}'
# ← order_id, status: approved (auto < 500 USD)

# 5. Sync to Odoo
curl -X POST https://localhost/api/odoo/sync -d '{"entity":"all"}'
# ← products, suppliers, procurement → Odoo purchase.order

# 6. مراقبة آفات
curl -X POST https://localhost/api/agriai/predict-pest-risk   -d '{"field_id":"field_new","crop_type":"wheat","growth_stage":"flowering"}'
# ← wheat_rust: medium risk — apply preventive fungicide

# 7. توقع إنتاج
curl -X POST https://localhost/api/agriai/predict-yield   -d '{"field_id":"field_new","crop_type":"wheat","field_area_ha":5,"ndvi_avg":0.72}'
# ← 5.42 ton/ha, revenue: $7588, confidence: 85%

# 8. استشارة ذكاء اصطناعي
curl -X POST https://localhost/api/rag/query   -d '{"question":"كيف أتعامل مع صدأ القمح؟"}'
# ← Qwen3 answer with sources from agricultural KB
```

---

## 📊 مراقبة الخدمات

```bash
# حالة جميع الخدمات
docker compose -f docker-compose.unified.yml ps

# سجلات خدمة معينة
docker compose -f docker-compose.unified.yml logs -f agriai-engine
docker compose -f docker-compose.unified.yml logs -f supervisor-agent
docker compose -f docker-compose.unified.yml logs -f odoo-bridge

# إعادة بناء خدمة واحدة
docker compose -f docker-compose.unified.yml up -d --build agriai-engine

# إيقاف الكل
docker compose -f docker-compose.unified.yml down

# إيقاف مع حذف البيانات (⚠️)
docker compose -f docker-compose.unified.yml down -v
```

---

## 🛡️ الأمان

| الميزة | التنفيذ |
|--------|---------|
| **TLS 1.2/1.3** | Nginx + Let's Encrypt |
| **JWT Authentication** | HS256, exp 24h |
| **RLS (Row Level Security)** | 25+ جداول في PostGIS |
| **Rate Limiting** | Redis-based (للتوسع) |
| **API Key for Odoo** | لا تخزين كلمات مرور |
| **Secrets in .env** | لا secrets في الكود |
| **Health Checks** | كل خدمة تفحص نفسها |

---

## 🔧 استكشاف الأخطاء

### خدمة لا تبدأ

```bash
# 1. فحص السجلات
docker compose logs <service_name> | tail -50

# 2. فحص الصحة
curl http://localhost:<port>/healthz

# 3. فحص الاعتماديات
docker compose ps | grep unhealthy

# 4. إعادة تشغيل
docker compose restart <service_name>
```

### قاعدة البيانات

```bash
# دخول PostGIS
docker compose exec postgis psql -U postgres -d sahool

# فحص الجداول
\dt

# فحص RLS
SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public';
```

### Ollama لا يستجيب

```bash
# سحب النموذج يدوياً
docker exec -it sahool-ollama ollama pull qwen3:32b
docker exec -it sahool-ollama ollama pull nomic-embed-text

# فحص النماذج
docker exec sahool-ollama ollama list
```

---

## 📦 الحزم المدمجة

| الحزمة | الحجم | المحتوى |
|--------|-------|---------|
| `sahool-v91-edge-ready.zip` | 24.2 KB | Infrastructure + Video + Actuator + Mesh |
| `sahool-v91-ai-gis-enhancement.zip` | 17.9 KB | Qwen3 RAG + ECharts GIS + Big Screen |
| `sahool-v91-odoo-bridge.zip` | 17.1 KB | Odoo ERP Sync + Workflow + Cost Ledger |
| `sahool-v91-market.zip` | 15.7 KB | Marketplace + Procurement + Price History |
| `sahool-v91-agriai-engine.zip` | ~20 KB | 5 AI Models: Soil + Crops + Irrigation + Pest + Yield |
| **→ `sahool-v91-unified.zip`** | **~30 KB** | **All above in one compose + nginx + setup script** |

---

## 🎯 خارطة الطريق (Roadmap)

| المرحلة | المدة | المهمة |
|---------|-------|--------|
| **الآن** | — | Unified Setup جاهز للتشغيل |
| **v9.2** | 2 أسابيع | Flutter App (Actuator UI + Barcode Scanner) |
| **v9.3** | 1 شهر | Vue3/React Frontend SPA حقيقي |
| **v9.4** | 1.5 شهر | Big Screen with real API connections |
| **v9.5** | 2 أشهر | Modbus/LoRa Gateway + Smart Machinery CAN bus |
| **v9.6** | 2.5 شهر | Carbon Calculator + FAO Sustainability Reports |
| **v10.0** | 3 أشهر | K8s Helm Charts + Multi-region Deployment |

---

**الخلاصة:** بأمر واحد `./scripts/setup_unified.sh`، تحصل على منصة SAHOOL v9.1 الكاملة — 20+ خدمة، 5 نماذج ذكاء اصطناعي زراعي، تكامل ERP، سوق B2B، تحكم آلي، كاميرات، وبوت Telegram — جاهزة للإنتاج خلال 48 ساعة.
