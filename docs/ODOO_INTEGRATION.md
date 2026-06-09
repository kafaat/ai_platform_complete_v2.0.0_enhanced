# SAHOOL v9.1 — Odoo ERP Integration Guide
> **التاريخ:** 2026-05-19  
> **الهدف:** ربط SAHOOL بـ Odoo ERP لإدارة المشتريات، المخزون، التكاليف، وسير العمل

---

## 🎯 لماذا Odoo + SAHOOL؟

| SAHOOL (قوي في) | Odoo (قوي في) | النتيجة بعد الربط |
|-----------------|---------------|-------------------|
| IoT + AI + فضاء | ERP + محاسبة | منصة زراعية متكاملة |
| Edge Inference | Inventory + Warehouse | مخزون ذكي |
| Sentinel-2 NDVI | Procurement + AP | مشتريات مبنية على البيانات |
| Local RAG (Qwen3) | Accounting + Cost Centers | تكاليف مركزية دقيقة |
| Flutter Field App | Sales + CRM | مبيعات من الحقل |

---

## 🏗️ بنية التكامل

```
┌─────────────────────────────────────────────────────────────┐
│  Odoo ERP (Docker / SaaS / On-Premise)                      │
│  ├─ Purchase (المشتريات)                                    │
│  ├─ Inventory (المخزون)                                     │
│  ├─ Accounting (المحاسبة)                                   │
│  ├─ Sales (المبيعات)                                        │
│  └─ Analytic Accounting (التكاليف المركزية)               │
│       API: JSON-RPC / XML-RPC (:8069)                        │
└──────────────────────┬────────────────────────────────────────┘
                       │ HTTP JSON-RPC
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  SAHOOL Odoo Bridge (:8126)                                 │
│  ├─ sync_products()        → Odoo → SAHOOL                  │
│  ├─ sync_suppliers()       → Odoo → SAHOOL                  │
│  ├─ sync_procurement()     → SAHOOL → Odoo (Purchase Order) │
│  ├─ sync_costs()           → SAHOOL → Odoo (Analytic Entry) │
│  └─ webhook listener       ← Odoo pushes (real-time)        │
└──────────────────────┬────────────────────────────────────────┘
                       │ asyncpg
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  SAHOOL PostGIS                                             │
│  ├─ procurement_orders (with odoo_sync_status)              │
│  ├─ field_cost_ledger (cost roll-up per hectare)            │
│  ├─ crop_batches (traceability + blockchain_tx)             │
│  ├─ workflow_instances (approval engine)                    │
│  └─ inventory_locations (multi-warehouse)                   │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚙️ إعداد Odoo

### 1. تثبيت Odoo (Docker)

```yaml
# docker-compose.odoo.yml
version: "3.8"
services:
  odoo:
    image: odoo:18.0
    ports: ["8069:8069"]
    environment:
      - HOST=odoo-db
      - USER=odoo
      - PASSWORD=myodoo
    volumes:
      - odoo-data:/var/lib/odoo
      - ./odoo-addons:/mnt/extra-addons
    depends_on: [odoo-db]

  odoo-db:
    image: postgres:15
    environment:
      - POSTGRES_DB=postgres
      - POSTGRES_PASSWORD=myodoo
      - POSTGRES_USER=odoo
      - PGDATA=/var/lib/postgresql/data/pgdata
    volumes:
      - odoo-db-data:/var/lib/postgresql/data/pgdata

volumes:
  odoo-data:
  odoo-db-data:
```

```bash
docker compose -f docker-compose.odoo.yml up -d
# افتح http://localhost:8069
# أنشئ قاعدة بيانات: sahool_erp
```

### 2. تفعيل الوحدات المطلوبة

في Odoo Apps، ثبّت:
- **Purchase** (المشتريات)
- **Inventory** (المخزون)
- **Accounting** (المحاسبة)
- **Analytic Accounting** (التكاليف المركزية)
- **Sales** (المبيعات)
- **Project** (لمهام الحقل)

### 3. إنشاء API Key (مستحسن بدلاً من كلمة المرور)

```
Odoo → Settings → Users → admin → Account Security → New API Key
```

انسخ المفتاح إلى `.env`:
```bash
ODOO_URL=http://odoo:8069
ODOO_DB=sahool_erp
ODOO_USER=admin
ODOO_API_KEY=your-long-api-key-here
```

---

## 🚀 تشغيل Bridge

### أضف إلى `docker-compose.light.yml`:

```yaml
  # ── Odoo Bridge ────────────────────────────────────────────
  odoo-bridge:
    build:
      context: .
      dockerfile: services/odoo-bridge/Dockerfile
    container_name: sahool-odoo-bridge
    restart: unless-stopped
    ports: ["8126:8000"]
    environment:
      DATABASE_URL: "postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@sahool-postgis:5432/sahool"
      ODOO_URL: "${ODOO_URL:-http://odoo:8069}"
      ODOO_DB: "${ODOO_DB:-sahool_erp}"
      ODOO_USER: "${ODOO_USER:-admin}"
      ODOO_PASSWORD: "${ODOO_PASSWORD:-admin}"
      ODOO_API_KEY: "${ODOO_API_KEY}"
      SAHOOL_API_URL: "http://sahool-auth:8000"
      SAHOOL_AGENT_TOKEN: "${SAHOOL_AGENT_TOKEN}"
      SYNC_INTERVAL_SEC: "300"
    depends_on:
      - postgis
      - auth-service
    networks: [sahool-net]
```

### شغّل:

```bash
docker compose -f docker-compose.light.yml up -d odoo-bridge
# افحص
 curl http://localhost:8126/healthz
 curl http://localhost:8126/config
```

---

## 📡 API Endpoints

### 1. فحص الاتصال

```bash
curl http://localhost:8126/config
```

**الرد:**
```json
{
  "url": "http://odoo:8069",
  "db": "sahool_erp",
  "user": "admin",
  "connected": true,
  "uid": 2,
  "version": "18.0"
}
```

### 2. تزامن يدوي

```bash
# كل المنتجات
 curl -X POST http://localhost:8126/sync   -H "Content-Type: application/json"   -d '{"entity":"products","direction":"odoo_to_sahool"}'

# كل الموردين
 curl -X POST http://localhost:8126/sync   -d '{"entity":"suppliers","direction":"odoo_to_sahool"}'

# دفع طلبات الشراء إلى Odoo
 curl -X POST http://localhost:8126/sync   -d '{"entity":"procurement","direction":"sahool_to_odoo"}'

# تزامن كامل
 curl -X POST http://localhost:8126/sync   -d '{"entity":"all","direction":"bidirectional"}'
```

### 3. استعراض سجلات التزامن

```bash
curl "http://localhost:8126/logs?entity=product.product&limit=20"
```

### 4. استعراض منتجات Odoo

```bash
curl http://localhost:8126/products?limit=10
```

---

## 🔄 التزامن التلقائي (Background)

الـ Bridge يُشغّل `periodic_sync()` كل **5 دقائق** (قابل للتعديل عبر `SYNC_INTERVAL_SEC`).

| الاتجاه | الكيان | التكرار | المنطق |
|---------|--------|---------|--------|
| Odoo → SAHOOL | products | 5 دقائق | `write_date > last_sync` |
| Odoo → SAHOOL | suppliers | 5 دقائق | `write_date > last_sync` |
| Odoo → SAHOOL | warehouses | 5 دقائق | full sync |
| SAHOOL → Odoo | procurement | 5 دقائق | `odoo_sync_status = 'pending'` |
| SAHOOL → Odoo | field_costs | 5 دقائق | `odoo_sync_status = 'pending'` |

---

## 🕸️ Webhook — تزامن فوري من Odoo

### إعداد Webhook في Odoo (Automation Rule)

```python
# في Odoo: Settings → Automation → Automated Actions
# Model: Purchase Order
# Trigger: On Update
# Action: Execute Python Code

import requests
import json

url = "http://sahool-odoo-bridge:8126/webhook/odoo"
payload = {
    "event": "purchase.order:confirmed",
    "model": "purchase.order",
    "record_id": record.id,
    "data": {
        "name": record.name,
        "partner_id": record.partner_id.id,
        "state": record.state,
        "amount_total": record.amount_total
    }
}
requests.post(url, json=payload, timeout=5)
```

### الرد في SAHOOL:

```json
{"received": true, "model": "purchase.order"}
```

---

## 💰 تتبع التكاليف — Cost Roll-up

### مثال: تكلفة هكتار القمح

```sql
-- تسجيل مدخلات الحقل
INSERT INTO field_cost_ledger (field_id, season, category, item_name, quantity, unit, unit_cost_usd)
VALUES
('field_A3', '2026-summer', 'input', 'يوريا 46%', 200, 'kg', 0.45),
('field_A3', '2026-summer', 'input', 'مبيد تربس', 3, 'liter', 12.50),
('field_A3', '2026-summer', 'labor', 'حصاد يدوي', 8, 'hour', 3.00),
('field_A3', '2026-summer', 'equipment', 'جرار — حرث', 2, 'hour', 15.00),
('field_A3', '2026-summer', 'water', 'ري بالتنقيط', 1200, 'm3', 0.08);

-- عرض التكلفة الشهرية
SELECT * FROM field_cost_summary
WHERE field_id = 'field_A3' AND season = '2026-summer';
```

**النتيجة:**
```
 field_id  | season       | month     | category  | total_cost_usd | distinct_inputs
-----------+--------------+-----------+-----------+----------------+----------------
 field_A3  | 2026-summer | 2026-03   | input     | 127.50         | 2
 field_A3  | 2026-summer | 2026-03   | labor     | 24.00          | 1
 field_A3  | 2026-summer | 2026-03   | equipment | 30.00          | 1
 field_A3  | 2026-summer | 2026-03   | water     | 96.00          | 1
```

**التكلفة الإجمالية للهكتار:**
```sql
SELECT SUM(total_cost_usd) / 5.0 AS cost_per_hectare_usd
FROM field_cost_ledger
WHERE field_id = 'field_A3' AND season = '2026-summer';
-- النتيجة: ~55.5 USD/هكتار
```

### دفع التكاليف إلى Odoo Analytic Accounting:

```bash
curl -X POST http://localhost:8126/sync -d '{"entity":"costs"}'
```

يُنشئ في Odoo:
- `account.analytic.line` بقيمة سالبة (تكلفة).
- مرتبطة بـ Analytic Account = `field_A3`.

---

## 📋 سير العمل — Workflow Engine

### مثال: موافقة على طلب شراء > 1000 USD

```sql
-- إنشاء طلب
INSERT INTO procurement_orders (tenant_id, status, total_cost_usd)
VALUES ('default', 'draft', 2500.00)
RETURNING order_id;

-- إنشاء instance workflow
INSERT INTO workflow_instances (workflow_name, document_type, document_id, current_state, tenant_id, priority)
VALUES ('procurement', 'procurement_order', 'uuid-here', 'proc_draft', 'default', 'high');
```

### الانتقالات:

| الحالة الحالية | الشرط | الدور المطلوب | الحالة التالية |
|----------------|-------|---------------|----------------|
| draft | — | — | pending |
| pending | amount < 5000 | manager | manager_approved |
| pending | amount ≥ 5000 | finance | finance_approved |
| manager_approved | — | — | ordered |
| finance_approved | — | — | ordered |
| pending | — | manager | rejected |

### API الموافقة:

```bash
curl -X POST http://localhost:8126/workflow/transition   -H "Content-Type: application/json"   -d '{
    "instance_id": "uuid-here",
    "to_state": "proc_manager_approved",
    "actor_id": 5,
    "actor_name": "أحمد المدير",
    "comment": "تمت الموافقة بعد مراجعة العرض"
  }'
```

---

## 🔗 تتبع المنتجات — Crop Batch Traceability

### إنشاء دفعة:

```sql
INSERT INTO crop_batches (tenant_id, field_id, crop_type, season, planting_date, certifications)
VALUES ('default', 'field_A3', 'wheat', '2026-summer', '2026-03-01', ARRAY['organic', 'GlobalGAP'])
RETURNING batch_id, barcode;
```

**الباركود التلقائي:** `SAH-2026-000001`

### إضافة حدث:

```sql
INSERT INTO crop_batch_events (batch_id, event_type, activity_name, inputs_used, location)
VALUES (
  'batch-uuid',
  'fertilization',
  'تسميد يوريا — المرحلة الأولى',
  '[{"product_id":"Urea-46","qty":100,"unit":"kg","batch_no":"LOT-2026-03"}]',
  ST_SetSRID(ST_MakePoint(44.21, 15.35), 4326)
);
```

### QR Code للمستهلك:

```
https://sahool.farm/trace/SAH-2026-000001
```

يُظهر:
- نوع المحصول + الحقل + التاريخ.
- جميع المدخلات (أسمدة/مبيدات) مع LOT numbers.
- شهادات الجودة.
- blockchain_tx (إن وجد).

---

## 📊 لوحة تحكم التكامل

افتح Big Screen → تبويب "ERP Integration":

| KPI | المصدر | التحديث |
|-----|--------|---------|
| طلبات الشراء قيد الموافقة | `workflow_instances` | Real-time |
| تكلفة الهكتار — هذا الموسم | `field_cost_summary` | 5 min |
| قيمة المخزون | Odoo `stock.quant` | 5 min |
| الموردين الجدد | `suppliers` | 5 min |
| دفعات المحصول القابلة للتتبع | `crop_batches` | Real-time |

---

## 🛡️ الأمان

1. **API Key:** استخدم `ODOO_API_KEY` بدلاً من كلمة المرور.
2. **Webhook Secret:** عيّن `WEBHOOK_SECRET` وتحقق من HMAC.
3. **RLS:** جميع الجداول الجديدة محمية بـ Row Level Security.
4. **Network:** Bridge يعمل داخل `sahool-net` فقط — لا يُعرض للإنترنت مباشرة.

---

## 🔧 استكشاف الأخطاء

### Bridge لا يتصل بـ Odoo:

```bash
# 1. فحص الشبكة
docker compose exec odoo-bridge curl -s http://odoo:8069

# 2. فحص الـ logs
docker compose logs -f odoo-bridge

# 3. التأكد من API Key
 docker compose exec odoo-bridge python -c "
import httpx, os
url = os.getenv('ODOO_URL') + '/jsonrpc'
payload = {'jsonrpc':'2.0','method':'call','params':{'service':'common','method':'authenticate','args':[os.getenv('ODOO_DB'), os.getenv('ODOO_USER'), os.getenv('ODOO_API_KEY'), {}]},'id':1}
print(httpx.post(url, json=payload).json())
"
```

### تكرار sync:

```sql
-- إعادة تعيين حالة التزامن
UPDATE odoo_sync_state SET last_sync_at = '1970-01-01' WHERE entity='product.product';
UPDATE procurement_orders SET odoo_sync_status='pending' WHERE status='approved';
```

---

## 📚 المراجع

- Odoo External API: https://www.odoo.com/documentation/18.0/developer/reference/external_api.html
- Odoo Docker: https://hub.docker.com/_/odoo
- NodCloud ERP (Gitee): https://gitee.com/yimiaoOpen/nodcloud
- ERPNext Agriculture: https://docs.erpnext.com/docs/user/manual/en/agriculture

---

**الخلاصة:** بربط SAHOOL بـ Odoo، تحصل على **ERP زراعي متكامل** — IoT/AI/فضاء من SAHOOL + محاسبة/مشتريات/مخزون/تكاليف من Odoo — مع تزامن ثنائي الاتجاه كل 5 دقائق.
