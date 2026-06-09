# SAHOOL v9.1 — AI & GIS Enhancement Pack
> **التاريخ:** 2026-05-19  
> **المصادر:** Gitee (FastBee, Frog, iDataV, IofTV-Screen) + FreeCodeCamp (Qwen3 RAG) + Medium (LangGraph Ollama)

---

## 🧠 1. تحسين الذكاء الاصطناعي — Local RAG (Qwen3 + Ollama)

### المشكلة في v9.0
- الـ Supervisor Agent يعتمد على OpenAI API (GPT-4) — تكلفة شهرية + تسريب بيانات.
- لا يوجد قاعدة معرفة زراعية عربية محلية.

### الحل: `services/local-ai-rag/`
**المصدر:** FreeCodeCamp tutorial on Qwen3 + Ollama + LangChain citeweb_search:12#5 + Medium LangGraph local RAG citeweb_search:12#6

| المكون | التقنية | الدور |
|--------|---------|-------|
| **LLM** | Qwen3 (8B / 32B / 70B) via Ollama | استشاري زراعي عربي/إنجليزي |
| **Embeddings** | nomic-embed-text via Ollama | تحويل النصوص إلى vectors |
| **Vector DB** | Qdrant (موجود في SAHOOL) | تخزين chunks |
| **Framework** | LangChain + RetrievalQA | RAG pipeline |
| **API** | FastAPI (:8125) | REST endpoint |

### API Endpoints
```bash
# 1. رفع مستندات (PDF/TXT/MD)
curl -X POST http://localhost:8125/ingest   -F "files=@agriculture_guide_ar.pdf"   -F "files=@pest_control_handbook.txt"   -F "tenant_id=farm_01"

# 2. استعلام RAG
 curl -X POST http://localhost:8125/query   -H "Content-Type: application/json"   -d '{
    "question": "كيف أتعامل مع تربس القمح في المرحلة المبكرة؟",
    "tenant_id": "farm_01",
    "k": 5
  }'
```

### الرد:
```json
{
  "question": "كيف أتعامل مع تربس القمح في المرحلة المبكرة؟",
  "answer": "يُنصح باستخدام المبيدات الحشرية النظامية... (مقتطف من دليل المكافحة)",
  "model": "qwen3:32b",
  "sources": [
    {"source": "pest_control_handbook.txt", "page": 45, "snippet": "..."}
  ]
}
```

### متطلبات العتاد (Hardware)
| النموذج | VRAM مطلوب | سرعة الرد | ملاحظة |
|---------|-----------|-----------|--------|
| qwen3:8b | 8-10 GB | ~2 ثانية | للاختبار |
| qwen3:32b | 24-28 GB | ~5 ثوانٍ | موصى به للإنتاج |
| qwen3:70b | 48-56 GB | ~8 ثوانٍ | دقة عالية |

> **الجهاز المستخدم:** GPU RTX 4090/5090 + 192GB RAM — يشغل 70B بسهولة.

---

## 🗺️ 2. عرض المؤشرات فوق الخرائط — ECharts + Leaflet

### المشكلة في v9.0
- لا يوجد طريقة لعرض NDVI أو رطوبة التربة أو بؤر الآفات **فوق الخريطة** بشكل تفاعلي.
- Grafana يعرض رسومات منفصلة، لا overlay GIS.

### الحل: `frontend/gis-overlay/index.html`
**المصدر:** Juejin article on ECharts + Leaflet extension citeweb_search:12#0 + Gitee iDataV big screen GIS citeweb_search:12#1

| الطبقة | التقنية | البيانات |
|--------|---------|----------|
| **NDVI Heatmap** | ECharts `heatmap` + `coordinateSystem: 'leaflet'` | Sentinel-2 10m grid |
| **Pest Scatter** | ECharts `effectScatter` (ripple) | Edge AI detections |
| **Soil Moisture** | ECharts `scatter` + labels | IoT sensors |
| **Field Boundaries** | ECharts `lines` (polyline) | GeoJSON farm polygons |
| **Base Map** | Leaflet + CartoDB Dark Matter | Tiles مجانية |

### المميزات التفاعلية
- ✅ **Toggle Layers:** أزرار لإظهار/إخفاء كل طبقة.
- ✅ **Tooltip:** hover يعرض NDVI value + Lat/Lng.
- ✅ **Ripple Effect:** بؤر الآفات تُظهر دوائر نبضية حمراء.
- ✅ **RTL:** واجهة عربية بالكامل.

### كيفية الاستخدام
```bash
# افتح مباشرة في المتصفح
firefox frontend/gis-overlay/index.html

# أو اعرضه عبر Nginx
location /gis/ {
    alias /app/frontend/gis-overlay/;
    index index.html;
}
```

---

## 📺 3. لوحة القيادة الكبيرة — Vue3 + ECharts Big Screen

### المشكلة في v9.0
- Grafana للـ DevOps فقط — لا يوجد **واجهة زراعية تفاعلية** للشاشات الكبيرة.

### الحل: `frontend/big-screen/index.html`
**المصدر:** Gitee IofTV-Screen-Vue3 citeweb_search:12#7 + Gitee big screen collection citeweb_search:12#8 + CSDN WebGIS big screen citeweb_search:12#3

| المنطقة | المكون | التقنية |
|---------|--------|---------|
| **Header** | شعار + ساعة + حالة النظام | Vue3 reactive |
| **Left Panel** | KPIs (NDVI, Soil, ET₀, Pest) + Yield Prediction + Device Status | ECharts line + pie |
| **Center Panel** | Map (heatmap scatter) + Live Camera Grid | ECharts + CSS Grid |
| **Right Panel** | Alerts feed + Weather 7-day + Carbon balance | ECharts bar/line |
| **Footer** | إحصائيات النظام | — |

### التصميم
- 🎨 **Dark Theme:** `#030c03` background + `#7fff7f` accents.
- 📐 **1920×1080 optimized:** rem scaling + flexible grid.
- 🔄 **Live updates:** كل 5 ثوانٍ (mock → WebSocket لاحقاً).
- 🖥️ **Full screen:** F11 للعرض على شاشات القيادة.

---

## 🏗️ التكامل مع docker-compose.light.yml

أضف إلى `docker-compose.light.yml`:

```yaml
  # ── Local AI RAG (NEW) ────────────────────────────────────
  local-ai-rag:
    build:
      context: .
      dockerfile: services/local-ai-rag/Dockerfile
    container_name: sahool-local-ai-rag
    restart: unless-stopped
    ports: ["8125:8000"]
    environment:
      OLLAMA_BASE_URL: "http://ollama:11434"
      LLM_MODEL: "qwen3:32b"
      EMBED_MODEL: "nomic-embed-text"
      QDRANT_URL: "http://sahool-qdrant:6333"
      COLLECTION_NAME: "sahool_agri_kb"
      NUM_CTX: "8192"
    depends_on:
      - qdrant
    networks: [sahool-net]

  # ── Ollama (NEW — run on host GPU) ─────────────────────────
  ollama:
    image: ollama/ollama:latest
    container_name: sahool-ollama
    restart: unless-stopped
    ports: ["11434:11434"]
    volumes:
      - ollama_models:/root/.ollama
    # For GPU passthrough (NVIDIA):
    # runtime: nvidia
    # environment:
    #   - NVIDIA_VISIBLE_DEVICES=all
    networks: [sahool-net]
```

> **ملاحظة:** Ollama يعمل أفضل على **Host** مع GPU passthrough (NVIDIA Container Toolkit). إذا لم يكن متاحاً، شغّله خارج Docker:
> ```bash
> ollama serve &
> ollama pull qwen3:32b
> ollama pull nomic-embed-text
> ```

---

## 📋 خطوات التفعيل

### الخطوة 1: تثبيت Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:32b
ollama pull nomic-embed-text
```

### الخطوة 2: بناء RAG Service
```bash
docker compose -f docker-compose.light.yml build local-ai-rag
```

### الخطوة 3: رفع قاعدة المعرفة
```bash
# ضع ملفات PDF/TXT في data/kb/
curl -X POST http://localhost:8125/ingest   -F "files=@data/kb/wheat_diseases_ar.pdf"   -F "tenant_id=default"
```

### الخطوة 4: اختبار الاستشاري
```bash
curl -X POST http://localhost:8125/query -d '{
  "question":"ما هي أعراض صدأ القمح؟",
  "tenant_id":"default"
}'
```

### الخطوة 5: عرض GIS Overlay
```bash
# افتح في المتصفح
firefox frontend/gis-overlay/index.html
```

### الخطوة 6: عرض Big Screen
```bash
# على شاشة القيادة (Kiosk mode)
firefox --kiosk frontend/big-screen/index.html
```

---

## 🎯 المقارنة مع المشاريع الصينية

| الميزة | Frog Smart Agri | FastBee | SAHOOL v9.1 (هذا الحزمة) |
|--------|-----------------|---------|--------------------------|
| AI RAG محلي | ❌ (API خارجي) | ❌ | ✅ Qwen3 + Ollama |
| GIS Overlay | ✅ Ezviz + Baidu | ❌ | ✅ ECharts + Leaflet |
| Big Screen | ✅ Goview (drag-drop) | ❌ | ✅ Vue3 + ECharts |
| IoT Actuation | ✅ Scene Linkage | ✅ Netty MQTT | ✅ (من v9.1 سابقاً) |
| Video RTSP | ✅ GB28181 | ❌ | ✅ ZLMediaKit |
| Mesh Network | ❌ | ❌ | ✅ ESP32 painlessMesh |
| Procurement | ❌ | ❌ | ✅ (من v9.1 سابقاً) |

---

## 🔮 التحسينات المستقبلية

1. **LangGraph Agentic RAG:** إضافة grader + rewriter + answer generator (مستوحى من Medium article).
2. **ECharts GL 3D:** عرض NDVI كـ 3D surface فوق الخريطة الطبوغرافية.
3. **WebRTC Live Stream:** دمج كاميرات ZLMediaKit مباشرة في Big Screen.
4. **Voice Input:** دعم Arabic STT (Whisper local) للاستشاري الصوتي.
5. **Auto-Report:** توليد تقارير PDF أسبوعية من Big Screen snapshots.

---

**المراجع:**
- Qwen3 Local RAG: FreeCodeCamp 2025 citeweb_search:12#5
- LangGraph Agentic RAG: Medium 2025 citeweb_search:12#6
- ECharts + Leaflet: Juejin 2023 citeweb_search:12#0
- Big Screen iDataV: Gitee citeweb_search:12#1
- IofTV-Screen-Vue3: Gitee/GitHub citeweb_search:12#7
