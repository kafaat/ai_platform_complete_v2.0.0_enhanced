# SAHOOL v9.1 — Edge-Ready Lightweight Integration

> **التاريخ:** 2026-05-19  
> **الهدف:** سد الفجوات المكتشفة في Gitee (FastBee + Frog + ZLMediaKit)  
> **الموارد:** 4 أنوية + 8GB RAM — قابل للتشغيل خلال 48 ساعة

---

## 🆕 ما الجديد في v9.1؟

| المكون | المصدر (Gitee) | الفائدة |
|--------|---------------|---------|
| **FastBee MQTT Broker** | `fastbee` (Netty مدمج) | بديل خفيف عن EMQX — يدير 10,000+ جهاز |
| **ZLMediaKit** | `ZLMediaKit` | بروكسي RTSP → WebRTC/FLV/HLS للكاميرات |
| **Video Processor** | مستوحى من Frog + AgriData | تحليل فيديو حي (YOLO frame-by-frame) |
| **Actuator Service** | مستوحى من Frog Scene Linkage | ربط تلقائي: sensor threshold → MQTT command |
| **ESP32 Mesh** | `painlessMesh` (AgriData) | شبكة ذاتية التشكيل للحقول البعيدة |
| **Procurement** | مستوحى من ERP زراعي | طلبات شراء + موردين + موافقات |

---

## 🏗️ البنية الجديدة

```
┌─────────────────────────────────────────────────────────────┐
│  Nginx (443) — SPA fallback + reverse proxy                │
├─────────────────────────────────────────────────────────────┤
│  SAHOOL Core (Python/FastAPI)                               │
│  ├─ auth-service (:8120)                                    │
│  ├─ supervisor-agent (:8096) — AI orchestration           │
│  ├─ sentinel/weather/wofost/market MCP (:8091-8094)       │
│  ├─ guardrails (:8097)                                      │
│  ├─ edge-inference (:8100) — ONNX/YOLO                    │
│  ├─ video-processor (:8110) ← NEW — RTSP/FLV/WebRTC       │
│  └─ actuator-service (:8111) ← NEW — Scene Linkage       │
├─────────────────────────────────────────────────────────────┤
│  IoT Layer                                                  │
│  ├─ FastBee (:8081 web + :1883 MQTT) ← NEW — Netty Broker │
│  ├─ ZLMediaKit (:8082 + :554 RTSP) ← NEW — Video Gateway  │
│  └─ ESP32 Mesh Nodes ← NEW — painlessMesh + DHT22 + FC28   │
├─────────────────────────────────────────────────────────────┤
│  Infrastructure (Light)                                   │
│  ├─ PostGIS (:5432) — Auth + Rules + Procurement          │
│  ├─ Redis (:6379) — Cache + Sessions                      │
│  ├─ NATS (:4222) — Events (indicators, satellite)         │
│  └─ MinIO (:9000) — Object storage                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 التشغيل السريع

```bash
# 1. استخرج الحزمة
cd sahool-v91-edge-ready

# 2. شغّل الإعداد (يولد .env تلقائياً)
chmod +x scripts/setup_light.sh
./scripts/setup_light.sh

# 3. افحص الحالة
docker compose -f docker-compose.light.yml ps

# 4. شاهد الـ logs
docker compose -f docker-compose.light.yml logs -f actuator-service
```

---

## 📡 إضافة كاميرا RTSP

```bash
curl -X POST http://localhost:8110/streams   -H "Content-Type: application/json"   -d '{
    "stream_id": "cam_north_01",
    "rtsp_url": "rtsp://admin:pass@192.168.1.100:554/live",
    "field_id": "field_01",
    "tenant_id": "default",
    "ai_enabled": true,
    "detection_interval_sec": 10
  }'
```

**الرد:**
```json
{
  "stream_id": "cam_north_01",
  "status": "starting",
  "source": "rtsp://admin:pass@192.168.1.100:554/live"
}
```

**مشاهدة مباشرة عبر ZLMediaKit:**
```
http://localhost:8082/live/cam_north_01.live.flv
```

---

## 🔧 إنشاء قاعدة ربط تلقائي (Scene Linkage)

```sql
-- في PostGIS:
INSERT INTO automation_rules (
  tenant_id, rule_name, trigger_sensor, trigger_operator,
  trigger_threshold, action_device, action_command,
  time_window_start, time_window_end
) VALUES (
  'default',
  'ري تلقائي — رطوبة منخفضة',
  'soil_moisture_pct',
  '<',
  30.0,
  'valve_field_01',
  'OPEN',
  '05:00:00',
  '19:00:00'
);
```

**المنطق:**
- إذا `soil_moisture_pct < 30%` → يرسل MQTT command `OPEN` إلى `valve_field_01`.
- لا يعمل خارج نافذة الوقت (5AM–7PM).
- cooldown 5 دقائق بين كل تشغيل.

---

## 🔌 برمجة ESP32 Mesh

1. افتح `firmware/esp32_mesh_gateway/esp32_mesh_gateway.ino` في Arduino IDE.
2. ثبّت المكتبات:
   - `painlessMesh` by Jeremy Garff
   - `PubSubClient` by Nick O'Leary
   - `DHT sensor library` by Adafruit
   - `ArduinoJson` by Benoit Blanchon
3. عدّل `WIFI_SSID` و `MQTT_SERVER`.
4. ارفع الكود إلى 3-10 وحدات ESP32.

**الوضع:**
- **Root node:** يتصل بـ WiFi + يرسل MQTT إلى FastBee.
- **Child nodes:** يرسلون بيانات المستشعرات عبر Mesh.
- **الفائدة:** لا يحتاج كل مستشعر إلى WiFi — يكفي أن يكون واحداً ضمن نطاق الـ Root.

---

## 📦 إدارة المشتريات (Procurement)

```sql
-- إضافة مورد
INSERT INTO suppliers (tenant_id, name, categories, rating)
VALUES ('default', 'مورد الأسمدة اليمني', ARRAY['fertilizer'], 4.5);

-- إنشاء طلب شراء
INSERT INTO procurement_orders (tenant_id, status, notes)
VALUES ('default', 'draft', 'طلب يوريا لموسم الصيف');

-- إضافة بنود
INSERT INTO procurement_order_items (order_id, item_name, category, quantity, unit_cost_usd)
SELECT order_id, 'يوريا 46%', 'fertilizer', 2000, 0.45
FROM procurement_orders WHERE status = 'draft' LIMIT 1;
```

---

## ⚖️ مقارنة الموارد: v9.0 الكامل vs v9.1 الخفيف

| المورد | v9.0 (كامل) | v9.1 (خفيف) | التوفير |
|--------|-------------|-------------|---------|
| الحاويات | 18+ | 12 | 33% |
| RAM مطلوب | 16GB+ | 8GB | 50% |
| CPU أنوية | 8+ | 4 | 50% |
| Disk | 50GB+ | 20GB | 60% |
| خدمات مراقبة | Prometheus+Grafana+Jaeger | Nginx logs فقط | 100% |
| Qdrant VectorDB | نعم | لا | — |
| TimescaleDB | نعم | لا (PostGIS عادي) | — |

---

## 🔗 التكامل مع v9.0 الكامل

إذا أردت العودة إلى الوضع الكامل لاحقاً:

```bash
# أوقف الخفيف
docker compose -f docker-compose.light.yml down

# شغّل الكامل
docker compose -f docker-compose.v9.yml up -d
```

**التوافق:**
- نفس قاعدة البيانات (PostGIS).
- نفس JWT_SECRET.
- `automation_rules` و `video_streams` تعملان في الوضعين.

---

## 📋 قائمة المهام التالية (Roadmap)

- [ ] **Flutter App:** إضافة شاشة "التحكم الآلي" (تشغيل/إيقاف الصمامات).
- [ ] **Telegram Bot:** أمر `/automation` لعرض rules + تفعيل/تعطيل.
- [ ] **Dashboard:** Goview-style drag & drop (مستوحى من Frog).
- [ ] **Firmware:** دعم Modbus-RTU عبر RS485 للمضخات الصناعية.
- [ ] **Video:** دعم GB28181 القياسي الصيني (للكاميرات Hikvision/Dahua).

---

**التوثيق التقني الكامل:**
- FastBee: https://gitee.com/beecue/fastbee
- ZLMediaKit: https://github.com/ZLMediaKit/ZLMediaKit
- painlessMesh: https://gitlab.com/painlessMesh/painlessMesh
- Frog Smart Agriculture: https://gitee.com/cuisiting/frog-smart-agriculture
