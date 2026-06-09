# SAHOOL v9.0 — الوثيقة التقنية الشاملة
## نظام الزراعة الذكي المُدمج — بنية 2026

> **الإصدار:** 9.0.0  
> **التاريخ:** 2026-05-19  
> **المؤلف:** فريق SAHOOL المعماري  
> **اللغة:** العربية (مع إشارات تقنية إنجليزية)  

---

## 1. الملخص التنفيذي

يُمثّل SAHOOL v9.0 تحولاً جوهرياً من **منصة خدمات منفصلة** (v8.0) إلى **نظام وكيلي ذكي متكامل** (Agentic Agricultural System). يجمع هذا الإصدار بين:

- **العمق الأكاديمي:** منهجية Agricultural Systems (Spedding, 1976) + Sensor Fusion (Plant Methods 2023)
- **القوة التقنية:** MCP Protocol 2026 + NVIDIA Agentic AI Stack + Edge AI
- **النضج التجاري:** سوق B2B + مجتمع رقمي + اعتمادات كربونية

### الفلسفة الجديدة: "Systems-First, Data-Driven, Community-Centric"

الزراعة ليست مجموعة تقنيات منفصلة، بل **نظام حي** مُتكامل من بيولوجيا + اقتصاد + مجتمع + سياسة.

---

## 2. البنية المعمارية — 5 طبقات

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  الطبقة ٥: السياسة والسوق (Policy & Market Layer)                           │
│  ├─ محاكي السياسات (Policy Simulator) — تأثير الدعم/الضريبة/الإعانات       │
│  ├─ سوق SAHOOL B2B (Forward Contracts + Carbon Credits)                      │
│  ├─ التمويل الزراعي (Digital Credit Scoring)                                │
│  └─ الإعانات الذكية (Auto-matching Subsidies)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  الطبقة ٤: المجتمع والمشاركة (Social & Community Layer)                       │
│  ├─ المجتمع الرقمي (Telegram/WhatsApp Groups + In-app Forum)                  │
│  ├─ المشاركة التشاركية (Participatory Modeling — المزارع يُعدّل النموذج)    │
│  ├─ سوق العمالة الموسمية (Labor Marketplace)                                  │
│  └─ تتبع البلوكتشين (Blockchain Traceability — من الحقل إلى المستهلك)        │
├─────────────────────────────────────────────────────────────────────────────┤
│  الطبقة ٣: وكيل الذكاء الاصطناعي (Agricultural AI Agent Layer)                │
│  ├─ LLM عربي زراعي (AraGPT/LLaMA-3.1-70B fine-tuned)                        │
│  ├─ VLM رؤية حاسوبية (YOLOv8-World / Agri-LLaVA — كشف الآفات والأمراض)       │
│  ├─ MCP Client (Unified Tool Interface — OAuth 2.1 + mTLS + Streamable HTTP) │
│  ├─ RAG: Qdrant/Milvus (FAO docs + Yemen local + WOFOST)                     │
│  ├─ Guardrails: SAHOOLGuardrails (3 tiers + Human-in-Loop + Diff Generator)  │
│  ├─ محلل المفاضلات (Pareto NSGA-II + شرح عربي)                               │
│  └─ محرر Workflow بصري (ComfyUI-inspired Node Editor)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  الطبقة ٢: دمج المستشعرات (Sensor Fusion Engine)                              │
│  ├─ Sentinel-2 L2A (BOA) — NDVI · EVI · Red Edge · SWIR (GDAL/rasterio)     │
│  ├─ Sentinel-1 GRD (VV/VH) — اختراق الغيوم/الليل                              │
│  ├─ UAV-LiDAR — CHM · Point Density · Canopy Cover (للبساتين)                 │
│  ├─ IoT Edge — رطوبة · NPK · EC · Temp (LoRa + MQTT Gateway)                  │
│  ├─ Weather — Hargreaves ET0 · Forecast · Historical (Open-Meteo + NOAA)      │
│  ├─ Vision — Drone RGB · Multispectral · Smartphone (Edge AI)                   │
│  └─ AGB Estimator (Random Forest R²=0.89 · 10m resolution)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  الطبقة ١: الفيزياء الحيوية (Bio-Physics Layer)                                │
│  ├─ WOFOST-RUE — نمو المحصول · GDD · Phenology · Harvest Index                 │
│  ├─ FAO-56 — الري والتبخر النتحي (ETc · Kc · Irrigation Scheduling)           │
│  ├─ تكامل المحاصيل-الحيوانات (Crop-Livestock Nutrient Cycle)                   │
│  ├─ الكربون — Soil Organic Carbon · Sequestration · Verra VCS methodology     │
│  └─ التربة — NPK · pH · Salinity · Bulk Density · Texture                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. الطبقة ١: الفيزياء الحيوية (Bio-Physics Layer)

### 3.1 WOFOST-RUE (World Food Studies Simulation)

| المكون | الوصف | المدخلات | المخرجات |
|--------|-------|----------|----------|
| **TSUM1** | درجات الحرارة المطلوبة للإنبات | Tmax, Tmin, Tbase | أيام حتى الإنبات |
| **TSUM2** | درجات الحرارة المطلوبة للنضج | Tmax, Tmin, Tbase | أيام حتى الحصاد |
| **LAI** | مؤشر مساحة الأوراق | RUE, PAR, stress | m² leaf / m² soil |
| **RUE** | كفاءة استخدام الإشعاع | Biomass / Intercepted PAR | g DM / MJ |
| **HI** | معامل الحصاد | Yield / Biomass | 0.35–0.75 |

**التكامل مع MCP:** `wofost_server.py` يُوفّر أدوات MCP:
- `run_wofost_simulation(crop, planting_date, soil_type, weather)`
- `get_crop_parameters(crop)`

### 3.2 FAO-56 (Irrigation & Evapotranspiration)

**معادلة Hargreaves-Samani (ET0):**
```
ET0 = 0.0023 × (Tmean + 17.8) × √Trange × Ra × 0.408
```

حيث:
- **Tmean** = (Tmax + Tmin) / 2
- **Trange** = Tmax − Tmin
- **Ra** = الإشعاع الفضائي (MJ/m²/day)

**ETc = ET0 × Kc**
حيث Kc يختلف حسب المحصول والمرحلة النموية.

### 3.3 تكامل المحاصيل-الحيوانات (Crop-Livestock Integration)

```
┌─────────────────────────────────────────┐
│  محصول (Crop)                           │
│  ├─ بقايا المحصول (Crop Residue)        │
│  │   └─ N, P, K → تربة (Soil)          │
│  │                                       │
│  ├─ علف (Fodder)                        │
│  │   └─ حيوان (Livestock)               │
│  │       └─ روث (Manure)                │
│  │           └─ N, P, K → تربة         │
│  │                                       │
│  └─ غطاء أرضي (Cover Crop)              │
│      └─ تثبيت النيتروجين (N-fixation)   │
│          └→ تربة                        │
└─────────────────────────────────────────┘
```

### 3.4 الكربون (Carbon Sequestration)

| المؤشر | الطريقة | المعيار |
|--------|---------|---------|
| **SOC** | Walkley-Black / Loss-on-Ignition | Mg C / ha |
| **AGB** | Random Forest Fusion (S2+S1+LiDAR) | kg DM / m² |
| **NPP** | MODIS / Sentinel-2 (GPP × 0.5) | g C / m² / year |
| **Carbon Credits** | Verra VCS Methodology VM0033 | tCO₂e / ha / year |

---

## 4. الطبقة ٢: دمج المستشعرات (Sensor Fusion Engine)

### 4.1 Sentinel-2 (Optical — MSI)

| النطاق | الدقة | الاستخدام في SAHOOL |
|--------|--------|---------------------|
| B02 (Blue) | 10m | تصحيح الغلاف الجوي |
| B03 (Green) | 10m | مؤشرات النبات العامة |
| B04 (Red) | 10m | NDVI, EVI, chlorophyll absorption |
| B05 (Red Edge 1) | 20m | حساسية عالية للكلوروفيل |
| B06 (Red Edge 2) | 20m | LAI estimation |
| B07 (Red Edge 3) | 20m | Red Edge Position |
| B08 (NIR) | 10m | NDVI, plant structure |
| B8A (Narrow NIR) | 20m | Red Edge NDVI |
| B11 (SWIR 1) | 20m | Water content, AGB proxy |
| B12 (SWIR 2) | 20m | Soil moisture, mineral content |

**معالجة البيانات:**
1. **Atmospheric Correction:** Sen2Cor / MAJA (BOA reflectance)
2. **Cloud Masking:** SCL (Scene Classification Layer) — استبعاد SCL=3,8,9
3. **NDVI:** `(B08 − B04) / (B08 + B04)`
4. **EVI:** `2.5 × (B08 − B04) / (B08 + 6×B04 − 7.5×B02 + 1)`
5. **GNDVI:** `(B08 − B03) / (B08 + B03)`

### 4.2 Sentinel-1 (SAR — Radar)

| المعلمة | القيمة | الاستخدام |
|---------|--------|-----------|
| **Band** | C-band (5.4 GHz) | اختراق الغطاء النباتي |
| **Polarization** | VV + VH | VV: structure, VH: volume |
| **Resolution** | 5×20m (GRD) | Field-scale monitoring |
| **Revisit** | 6 أيام (2 أقمار) | All-weather, day/night |

**المؤشرات المُستخرجة:**
- **VV/VH ratio:** حساسية لتركيبة الغطاء النباتي
- **Radar Vegetation Index (RVI):** `4×VH / (VV + VH)`
- **Backscatter difference:** تغيرات الرطوبة

### 4.3 UAV-LiDAR (Airborne Laser Scanning)

| المعلمة | الدقة | الاستخدام |
|---------|--------|-----------|
| **Point Density** | 10–50 pts/m² | Canopy structure |
| **CHM (Canopy Height Model)** | ~0.5m | Biomass estimation |
| **DSM/DTM** | ~0.1m | Terrain analysis |
| **Intensity** | 8-bit | Surface reflectance |

**المتغيرات المُستخرجة (21 variable — من ورقة Plant Methods):**
- Hmax, Hmean, Hmedian, Hstd
- Canopy Cover (%)
- LAI (LiDAR-derived)
- Point Density (pts/m²)
- Gap Fraction
- Rugosity

### 4.4 IoT Edge (LoRa + MQTT)

```
┌─────────────────────────────────────────┐
│  مستشعر التربة (Soil Sensor Node)       │
│  ├─ رطوبة @ 10cm, 20cm, 30cm            │
│  ├─ درجة حرارة التربة                   │
│  ├─ EC (Electrical Conductivity)         │
│  ├─ NPK (Nitrate, Phosphate, Potassium) │
│  └─ pH                                   │
│         ↕️ LoRa (868/915 MHz)            │
│  Gateway (Raspberry Pi 5 + LoRa HAT)     │
│         ↕️ MQTT over 4G/WiFi             │
│  SAHOOL Cloud (NATS JetStream)           │
└─────────────────────────────────────────┘
```

### 4.5 AGB Estimator (Random Forest Fusion)

**النموذج:** Random Forest Regressor (scikit-learn)
**الميزات (33 feature):**
- Sentinel-2: NDVI, EVI, SAVI, NDWI, GNDVI, Red Edge (3 bands), SWIR (2 bands)
- Sentinel-1: VV, VH, VV/VH ratio, RVI
- LiDAR: CHM max/mean/median, Canopy Cover, Point Density, LAI
- IoT: Soil moisture, Temperature, EC
- Weather: ET0, Precipitation, GDD

**الأداء (من ورقة Plant Methods):**
| النموذج | R² | RMSE (Mg/ha) |
|---------|-----|--------------|
| LiDAR فقط | 0.75 | ~18 |
| Sentinel-2 فقط | 0.60 | ~25 |
| Sentinel-1 فقط | 0.55 | ~28 |
| LiDAR + S2 | 0.85 | ~14 |
| **LiDAR + S2 + S1** | **0.89** | **~11** |

---

## 5. الطبقة ٣: وكيل الذكاء الاصطناعي (AI Agent Layer)

### 5.1 البنية المعمارية للوكيل

```
┌─────────────────────────────────────────┐
│  Supervisor Agent (Hierarchical Router) │
│  ├─ Intent Classification (Arabic/EN)  │
│  ├─ Domain Routing                       │
│  ├─ Conflict Resolution                  │
│  └─ Result Aggregation                   │
├─────────────────────────────────────────┤
│  Skill Libraries (Domain-Specific)        │
│  ├─ RemoteSensingSkill (NDVI · SAR · CHM)│
│  ├─ CropModelSkill (WOFOST · Irrigation)│
│  ├─ MarketSkill (Prices · Contracts)     │
│  └─ AdvisorySkill (Pest · Disease · Q&A)│
├─────────────────────────────────────────┤
│  MCP Client (Unified Tool Interface)    │
│  ├─ sentinel-hub-mcp (:8091)            │
│  ├─ weather-mcp (:8092)                  │
│  ├─ wofost-mcp (:8093)                   │
│  └─ market-mcp (:8094)                   │
├─────────────────────────────────────────┤
│  LLM + VLM + RAG + Guardrails           │
│  ├─ LLM: AraGPT/LLaMA-3.1-70B (Arabic)  │
│  ├─ VLM: Agri-LLaVA / YOLOv8-World      │
│  ├─ RAG: Qdrant VectorDB (FAO + Yemen)  │
│  └─ Guardrails: SAHOOLGuardrails (:8097) │
└─────────────────────────────────────────┘
```

### 5.2 MCP Protocol 2026 — المواصفات التقنية

**الإصدار:** MCP 2025-06-18 (Streamable HTTP)
**الأمان:** OAuth 2.1 + PKCE + mTLS
**النقل:** Streamable HTTP (replaces deprecated SSE)

**الأدوات المُعرّفة:**

| الأداة | الخادم | المدخلات | المخرجات |
|--------|--------|----------|----------|
| `fetch_sentinel2_l2a` | sentinel-hub | field_id, date_range, bands, cloud_cover_max | TIFF raster + metadata |
| `fetch_sentinel1_grd` | sentinel-hub | field_id, date_range, polarization | TIFF raster + metadata |
| `compute_ndvi` | sentinel-hub | field_id, date | NDVI map + statistics |
| `get_weather_forecast` | weather | lat, lon, days, hourly_vars | Daily + hourly forecast |
| `calculate_hargreaves_et0` | weather | lat, lon, date, Tmax, Tmin, Ra | ET0 mm/day |
| `get_historical_weather` | weather | lat, lon, start_date, end_date | Historical daily data |
| `run_wofost_simulation` | wofost | crop, planting_date, soil_type, weather | Yield, biomass, water, phenology |
| `get_crop_parameters` | wofost | crop | WOFOST parameters (TSUM, HI, RUE, etc.) |
| `get_market_price` | market | crop, market, date | Price YER/kg + USD/kg + trend |
| `create_forward_contract` | market | farmer_id, field_id, crop, yield, harvest_date | Contract ID + value + buyer matches |
| `get_price_trend` | market | crop, market | 30-day trend + forecast |

### 5.3 Guardrails Engine — 3 طبقات + Human-in-Loop

**الطبقة ١: Chemical Safety**
- **Banned Substances:** 13 مادة محظورة دولياً (Stockholm Convention)
- **Max Dosage:** حدود آمنة لـ 7 مبيدات شائعة (glyphosate, chlorpyrifos, imidacloprid, mancozeb, propiconazole, abamectin, sulfur)
- **Crop Restrictions:** مبيدات محظورة على محاصيل معينة
- **Buffer Zones:** مسافة آمنة من المساكن والمياه
- **Re-entry Intervals:** فترة حظر الدخول بعد الرش

**الطبقة ٢: Environmental Safety**
- **Water Limits:** حدود سحب المياه الجوفية/السطحية (m³/ha/season)
- **Salinity Risk:** EC irrigation + soil EC monitoring
- **Carbon Budget:** kg CO2e/season by crop
- **Soil Health:** pH, organic matter, erosion risk

**الطبقة ٣: Economic Safety**
- **Investment Capacity:** Max 30% of annual revenue per action
- **ROI Threshold:** Minimum 15% return on investment
- **Debt-to-Income:** Max 50% ratio
- **Cash Reserve:** Minimum 2 months operating expenses

**Human-in-the-Loop:**
- **MEDIUM risk:** 1 expert approval
- **HIGH risk:** 2 expert approvals
- **CRITICAL risk:** 3 expert approvals + admin escalation
- **Auto-reject:** After 2 escalations without response (48h timeout)

### 5.4 محلل المفاضلات (Pareto Trade-off Optimizer)

**الخوارزمية:** NSGA-II (Non-dominated Sorting Genetic Algorithm II)
**المتغيرات:** [irrigation_mm, N_kg, P_kg, K_kg, harvest_date_offset]
**الأهداف:**
1. Maximize Yield (kg/ha)
2. Maximize Profit (YER/ha)
3. Minimize Water Use (m³/ha)
4. Minimize Carbon Footprint (kg CO2e/ha)
5. Minimize Risk Score

**المخرجات:**
- Pareto Front (10 non-dominated solutions)
- Recommended solution (balanced composite score)
- Arabic trade-off explanation

---

## 6. الطبقة ٤: المجتمع والمشاركة

### 6.1 Telegram Bot — "مزرعتك في جيبك"

**الأوامر:**
- `/start` — التسجيل وربط الحقل
- `/ndvi` — طلب تقرير NDVI
- `/weather` — تنبؤ جوي 7 أيام
- `/pest` — إرسال صورة آفة للتشخيص
- `/market` — أسعار السوق اليوم
- `/contract` — إنشاء عقد آجل
- `/community` — ربط بمجموعة المحصول
- `/advice` — استشارة الـ AI Agent
- `/help` — قائمة الأوامر

### 6.2 سوق SAHOOL B2B

**Forward Contracts:**
1. المزارع يُقدّر إنتاجه (من Fusion Engine)
2. يُحدّد سعراً أدنى (min_price)
3. النظام يُطابق مع مشترين (buyer matching)
4. يُنشئ عقداً آجلاً (pre-harvest sale)
5. يُحسب اعتمادات كربونية محتملة

**Carbon Credits:**
- Verra VCS VM0033 methodology
- tCO2e = AGB × 0.5 × 44/12 (conversion)
- Price: $5–15/tCO2e (market dependent)

---

## 7. الطبقة ٥: السياسات والسوق

### 7.1 محاكي السياسات (Policy Simulator)

**السيناريوهات:**
- **Subsidy Impact:** ماذا لو زادت الإعانة 10%؟ 20%؟ 50%؟
- **Tax Impact:** تأثير ضريبة على المبيدات/المياه
- **Trade Policy:** تأثير حظر استيراد/تصدير
- **Climate Adaptation:** تأثير تغير المناخ على المحاصيل

**المخرجات:**
- تغير الربح (%)
- احتمالية تبديل المحصول
- تغير استهلاك المياه
- التكلفة الحكومية
- معدل التبني (adoption rate)

---

## 8. البنية التحتية والنشر (Infrastructure & Deployment)

### 8.1 خارطة المنافذ (Port Mapping)

| الخدمة | المنفذ | الوصف |
|--------|--------|-------|
| Nginx Gateway | 80/443 | Reverse proxy + SSL + SPA fallback |
| Auth Service | 8120 | JWT + bcrypt + tenant isolation |
| Supervisor Agent | 8096 | AI orchestration + MCP client |
| Sentinel Hub MCP | 8091 | Satellite data (S2 + S1) |
| Weather MCP | 8092 | Forecast + ET0 + historical |
| WOFOST MCP | 8093 | Crop simulation |
| Market MCP | 8094 | Prices + contracts |
| Guardrails Engine | 8097 | Safety validation + HIL |
| Edge Inference | 8100 | ARM64 on-device AI |
| PostgreSQL+PostGIS | 5432 | Main database + RLS |
| Redis | 6379 | Cache + sessions + pub/sub |
| MinIO | 9000 | Object storage (images, rasters) |
| Qdrant | 6333 | Vector database (RAG) |
| NATS JetStream | 4222 | Event streaming |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3001 | Dashboards |

### 8.2 Docker Compose (Production)

```yaml
# docker-compose.prod.yml (مُختصر)
version: "3.8"
services:
  nginx:
    image: nginx:alpine
    ports: ["80:80", "443:443"]
    volumes: ["./nginx.conf:/etc/nginx/nginx.conf:ro"]
    depends_on: [supervisor-agent, auth-service]

  supervisor-agent:
    build: ./supervisor_agent
    ports: ["8096:8000"]
    environment:
      - SAHOOL_AGENT_TOKEN=${SAHOOL_AGENT_TOKEN}
      - MCP_SENTINEL_HUB_URL=http://sentinel-hub-mcp:8091
      - MCP_WEATHER_URL=http://weather-mcp:8092
      - MCP_WOFOST_URL=http://wofost-mcp:8093
      - MCP_MARKET_URL=http://market-mcp:8094
      - GUARDRAILS_URL=http://guardrails:8097
    depends_on: [sentinel-hub-mcp, weather-mcp, wofost-mcp, market-mcp, guardrails]

  sentinel-hub-mcp:
    build: ./mcp_servers
    ports: ["8091:8000"]
    environment:
      - SH_CLIENT_ID=${SH_CLIENT_ID}
      - SH_CLIENT_SECRET=${SH_CLIENT_SECRET}
      - JWT_SECRET=${JWT_SECRET}

  guardrails:
    build: ./guardrails_engine
    ports: ["8097:8000"]
    environment:
      - JWT_SECRET=${JWT_SECRET}

  edge-inference:
    build:
      context: ./edge_inference
      dockerfile: Dockerfile.arm64
    ports: ["8100:8000"]
    environment:
      - EDGE_DEVICE=rpi5
      - OFFLINE_MODE=false
      - SAHOOL_CLOUD_URL=https://api.sahool.local
      - EDGE_SYNC_TOKEN=${EDGE_SYNC_TOKEN}
    volumes:
      - ./models:/models:ro
      - ./edge-data:/data

  # ... (other services)
```

### 8.3 Edge Deployment (Raspberry Pi 5 / Jetson Orin)

```bash
# Build for ARM64
docker buildx build --platform linux/arm64 \
  -f edge_inference/Dockerfile.arm64 \
  -t sahool/edge-inference:arm64-latest \
  ./edge_inference

# Deploy on Raspberry Pi 5
docker run -d \
  --name sahool-edge \
  -p 8100:8100 \
  -v /mnt/models:/models:ro \
  -v /mnt/data:/data \
  -e EDGE_DEVICE=rpi5 \
  -e OFFLINE_MODE=true \
  sahool/edge-inference:arm64-latest
```

---

## 9. الأمان (Security)

### 9.1 OAuth 2.1 + PKCE

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐
│  Client │────→│ Auth Server │────→│  MCP Server  │
│ (Agent) │     │ (SAHOOL)    │     │ (Resource)   │
└─────────┘     └─────────────┘     └─────────────┘
      │                │                  │
      │ 1. Auth Request│                  │
      │ + code_challenge│                  │
      │────────────────→│                  │
      │                │                  │
      │ 2. Auth Code   │                  │
      │←────────────────│                  │
      │                │                  │
      │ 3. Token Request│                 │
      │ + code_verifier │                 │
      │────────────────→│                  │
      │                │                  │
      │ 4. Access Token│                  │
      │←────────────────│                  │
      │                │                  │
      │ 5. API Call    │                  │
      │ + Bearer Token │                 │
      │──────────────────────────────────→│
      │                │                  │
      │ 6. Resource    │                  │
      │←──────────────────────────────────│
```

### 9.2 Row-Level Security (RLS) — PostgreSQL

```sql
-- Tenant isolation policy
CREATE POLICY tenant_isolation ON fields
    USING (tenant_id = current_setting('app.current_tenant')::UUID);

-- Enable on all tables
ALTER TABLE fields ENABLE ROW LEVEL SECURITY;
ALTER TABLE crop_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE soil_readings ENABLE ROW LEVEL SECURITY;
-- ... (all tenant-scoped tables)
```

### 9.3 Guardrails — Defense in Depth

| الطبقة | المهاجم | الدفاع |
|--------|---------|--------|
| **Network** | MITM, sniffing | mTLS + OAuth 2.1 |
| **Application** | SQL Injection | Parameterized queries + RLS |
| **AI** | Prompt injection | NeMo-like guardrails + input sanitization |
| **Chemical** | Unsafe recommendations | Banned substance DB + dosage limits |
| **Economic** | Financial harm | Investment limits + ROI thresholds |
| **Human** | Expert override | HIL workflow + audit trail |

---

## 10. المراقبة والملاحظة (Observability)

### 10.1 المؤشرات الرئيسية (KPIs)

| المؤشر | الهدف | الأداة |
|--------|-------|--------|
| **API Latency (p95)** | < 200ms | Prometheus + Grafana |
| **MCP Tool Success Rate** | > 99% | Custom metrics |
| **Guardrails Block Rate** | < 5% | Guardrails engine |
| **HIL Approval Time** | < 4h (MEDIUM), < 24h (HIGH) | Workflow tracking |
| **Edge Inference Time** | < 5s (RPI5), < 2s (Jetson) | Edge telemetry |
| **NDVI Data Freshness** | < 5 days | Sentinel-2 monitoring |
| **Yield Prediction Accuracy** | R² > 0.85 | Ground truth validation |
| **Farmer Adoption Rate** | > 60% (Year 1) | Analytics |

### 10.2 Distributed Tracing (OpenTelemetry)

```python
# Example trace through the system
Trace: farm_optimization_request
├── Span: supervisor_agent.classify_intent (15ms)
├── Span: mcp_client.call_tools_parallel (120ms)
│   ├── Span: sentinel-hub.fetch_sentinel2 (80ms)
│   ├── Span: weather.get_forecast (25ms)
│   └── Span: wofost.simulate (35ms)
├── Span: guardrails.validate (45ms)
│   ├── Span: chemical_tier.check (10ms)
│   ├── Span: environmental_tier.check (15ms)
│   └── Span: economic_tier.check (20ms)
└── Span: response_formatting (5ms)
```

---

## 11. خارطة طريق التنفيذ (12 شهراً)

### المرحلة ١: Foundation + MCP + حقيقية (شهر ١–٣)

| الأسبوع | المهمة | المخرج |
|---------|--------|--------|
| 1–2 | إصلاح Docker Build + Auth port + DB schema | Images قابلة للبناء |
| 3–4 | بناء sentinel-hub-mcp (S2 + S1 + OAuth 2.1) | بيانات فضائية حقيقية |
| 5–6 | بناء weather-mcp + wofost-mcp + market-mcp | أدوات MCP كاملة |
| 7–8 | GDAL/rasterio integration + NDVI حقيقي | خرائط NDVI من Sentinel-2 |
| 9–10 | Edge AI prototype (RPI5 + MobileViT) | Offline inference |
| 11–12 | اختبار تكامل + Ground Truth (5 حقول) | Dataset أولي |

### المرحلة ٢: AI Orchestration + VLM (شهر ٤–٦)

| الأسبوع | المهمة | المخرج |
|---------|--------|--------|
| 13–15 | Supervisor Agent (Hierarchical Routing) | Orchestrator يعمل |
| 16–18 | LLM fine-tuning (Arabic agriculture) | AraGPT/LLaMA-8B |
| 19–21 | VLM fine-tuning (Yemen pests) | Agri-LLaVA local |
| 22–24 | RAG + Qdrant + Guardrails | Knowledge base + safety |

### المرحلة ٣: Fusion + Visual Editor + Mobile (شهر ٧–٩)

| الأسبوع | المهمة | المخرج |
|---------|--------|--------|
| 25–28 | Sensor Fusion Engine (S2+S1+IoT+Weather) | Digital Twin |
| 29–32 | AGB Random Forest training (20 Yemen fields) | Model .pkl |
| 33–36 | Visual Workflow Editor (React-Flow) | Drag & Drop UI |
| 37–40 | Telegram Bot (full) + Flutter App MVP | Farmer interfaces |

### المرحلة ٤: Market + Policy + Scale (شهر ١٠–١٢)

| الأسبوع | المهمة | المخرج |
|---------|--------|--------|
| 41–44 | B2B Marketplace + Forward Contracts | Market service |
| 45–48 | Policy Simulator + Subsidy Matcher | Government tool |
| 49–52 | Carbon Credit Calculator + Verra VCS | Carbon trading |
| 53–56 | Blockchain Traceability + Living Labs (30 farms) | Production validation |

---

## 12. الخلاصة

SAHOOL v9.0 ليس مجرد تحديث تقني — بل هو **تحول معماري** يُحوّل المنصة من:
- **خدمات منفصلة** → **نظام وكيلي متكامل**
- **محاكاة وهمية** → **بيانات فضائية حقيقية**
- **توصيات منفردة** → **تحليل مفاضلات متعدد الأهداف**
- **منصة تقنية** → **نظام بيئي زراعي (Ecosystem)**

**الرباعي الذهبي للانطلاق:**
1. **MCP Servers** — بيانات حقيقية + context-aware
2. **Hybrid Agent** — 54% أقل tokens + 50% أقل latency
3. **Edge AI** — يعمل offline + كشف آفات حقيقي
4. **Guardrails + HIL** — أمان + ثقة المزارع

**الرؤية:** أن يصبح SAHOOL **"المنصة الزراعية العربية"** — من اليمن إلى المغرب، من الحقل إلى السوق، من البذرة إلى الكربون.

---

**التوثيق التقني الكامل:**
- MCP Protocol: https://modelcontextprotocol.io/
- NVIDIA Agent Toolkit: https://developer.nvidia.com/agent-toolkit
- WOFOST: https://www.wur.nl/en/research-results/research-institutes/plant-research/contents/wageningen-crop-growth-modelling-system-wofost.htm
- Sentinel Hub: https://www.sentinel-hub.com/
- Open-Meteo: https://open-meteo.com/
- Verra VCS: https://verra.org/programs/verified-carbon-standard/
