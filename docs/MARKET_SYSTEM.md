# SAHOOL v9.1 — Market System (Agricultural Marketplace + Procurement + Price Intelligence)
> **التاريخ:** 2026-05-19  
> **الحالة:** ✅ مُنفَّذ بالكامل — جاهز للبناء والتشغيل

---

## 🎯 ما تم إنجازه

| المكون | الحالة | الملف |
|--------|--------|-------|
| **Market MCP Server** | ✅ كامل | `services/mcp_servers/market_server.py` |
| **Database Schema** | ✅ 7 جداول + بيانات أولية | `migrations/v9_market.sql` |
| **MCP Tools** | ✅ 8 أدوات | داخل `market_server.py` |
| **REST API** | ✅ مباشر للـ Flutter/Web | نفس الملف |
| **Dockerfile** | ✅ مشترك لكل MCP | `services/mcp_servers/Dockerfile` |
| **Odoo Sync Ready** | ✅ أعمدة جاهزة | `odoo_product_id`, `odoo_partner_id`, `odoo_purchase_order_id` |

---

## 🏗️ البنية

```
┌─────────────────────────────────────────────────────────────┐
│  Market MCP Server (:8094)                                  │
│  ├─ /v1/mcp/tools/list   — 8 tools (MCP Protocol)          │
│  ├─ /v1/mcp/tools/call   — تنفيذ الأدوات                   │
│  ├─ /v1/products         — REST: بحث منتجات                  │
│  ├─ /v1/suppliers/{id}      — REST: تفاصيل مورد               │
│  ├─ /v1/procurement         — REST: إنشاء طلب شراء            │
│  ├─ /v1/procurement/{id}    — REST: حالة الطلب                │
│  ├─ /v1/sales               — REST: إنشاء/بحث عروض البيع      │
│  ├─ /v1/price-history/{cat} — REST: تاريخ الأسعار             │
│  └─ /v1/analytics/{tenant}  — REST: لوحة تحليلات              │
└──────────────────────┬──────────────────────────────────────┘
                       │ asyncpg
                       ▼
              ┌─────────────────┐
              │  PostGIS        │
              │  market_*       │
              └─────────────────┘
```

---

## 📦 الجداول (7 tables)

| الجدول | الغرض | السجلات الأولية |
|--------|-------|-----------------|
| `market_suppliers` | دليل الموردين | 3 (أسمدة اليمن، بذور الخليج، سينجنتا) |
| `market_products` | كتالوج المنتجات | 4 (يوريا 46%, NPK 15-15-15, بذور قمح, جلايفوسات) |
| `market_price_history` | تاريخ أسعار | فارغ (يُملأ عبر API أو يدوياً) |
| `market_procurement_orders` | طلبات الشراء | فارغ |
| `market_procurement_items` | بنود الطلب | فارغ |
| `market_sales_listings` | عروض بيع المحاصيل | فارغ |
| `market_analytics_snapshots` | لقطات تحليلية | فارغ |

---

## 🔌 MCP Tools (8 أدوات)

### 1. `market_search_products`
بحث في كتالوج المنتجات باسم أو صنف أو سعر أقصى.

### 2. `market_get_supplier`
تفاصيل مورد + قائمة منتجاته.

### 3. `market_create_procurement`
إنشاء طلب شراء متعدد البنود مع **موافقة تلقائية** إذا كان المبلغ ≤ 500 USD.

### 4. `market_get_procurement_status`
متابعة حالة الطلب + البنود + رقم Odoo (إن وجد).

### 5. `market_create_sales_listing`
عرض محصول للبيع في السوق (B2B) مع ربط batch للتتبع.

### 6. `market_search_sales`
بحث عروض البيع حسب نوع المحصول + الجودة + السعر.

### 7. `market_price_history`
تاريخ أسعار سلعة (أسبوعي/شهري) — قمح، شعير، تمور، يوريا، سولار...

### 8. `market_analytics_dashboard`
لوحة تحليلات: مشتريات، مبيعات، مخزون، تنبيهات أسعار.

---

## 🚀 التشغيل

### 1. تطبيق Migration

```bash
# داخل حاوية PostGIS
docker compose exec -T postgis psql -U postgres -d sahool -f /docker-entrypoint-initdb.d/v9_market.sql
```

أو عبر `setup_light.sh` (يُشغّل تلقائياً إذا كان الملف في `migrations/`).

### 2. بناء وتشغيل

```bash
# market-mcp موجود بالفعل في docker-compose.light.yml
docker compose -f docker-compose.light.yml up -d market-mcp

# فحص
 curl http://localhost:8094/healthz
 curl http://localhost:8094/v1/mcp/tools/list
```

### 3. اختبار REST API

```bash
# بحث منتجات
curl "http://localhost:8094/v1/products?q=يوريا&limit=5"

# تفاصيل مورد
curl http://localhost:8094/v1/suppliers/11111111-1111-1111-1111-111111111111

# إنشاء طلب شراء
curl -X POST http://localhost:8094/v1/procurement   -H "Content-Type: application/json"   -d '{
    "tenant_id": "00000000-0000-0000-0000-000000000000",
    "field_id": "field_A3",
    "items": [
      {"product_name": "يوريا 46%", "quantity": 2000, "unit": "kg", "max_unit_price_usd": 0.50},
      {"product_name": "بذور قمح صنعاء", "quantity": 500, "unit": "kg", "max_unit_price_usd": 1.30}
    ],
    "delivery_date": "2026-06-01",
    "notes": "موسم صيف 2026"
  }'

# عرض محصول للبيع
curl -X POST http://localhost:8094/v1/sales   -H "Content-Type: application/json"   -d '{
    "tenant_id": "00000000-0000-0000-0000-000000000000",
    "crop_type": "قمح",
    "quantity_kg": 50000,
    "price_per_kg_usd": 0.35,
    "quality_grade": "A",
    "pickup_location": "حقل A3 - صنعاء"
  }'

# تحليلات
curl http://localhost:8094/v1/analytics/00000000-0000-0000-0000-000000000000
```

---

## 🔗 التكامل مع Odoo Bridge

الجداول تحتوي على أعمدة Odoo جاهزة:

| العمود | الجدول | الوصف |
|--------|--------|-------|
| `odoo_partner_id` | `market_suppliers` | ربط المورد بـ `res.partner` |
| `odoo_product_id` | `market_products` | ربط المنتج بـ `product.product` |
| `odoo_purchase_order_id` | `market_procurement_orders` | ربط الطلب بـ `purchase.order` |

### سير العمل:
```
1. market_create_procurement (SAHOOL) → order_id
2. Odoo Bridge (كل 5 دقائق) → يرى `status='approved'` + `odoo_purchase_order_id IS NULL`
3. ينشئ `purchase.order` في Odoo
4. يحدث `market_procurement_orders.odoo_purchase_order_id`
5. عند تحديث Odoo → Webhook → يحدث `status` في SAHOOL
```

---

## 🌐 التكامل مع Supervisor Agent

الـ Supervisor Agent يستطيع استدعاء أدوات السوق عبر MCP:

```python
# داخل supervisor-agent
# عندما يطلب المستخدم: "اشترِ 2000 كغ يوريا لحقل A3"

mcp_call("market_search_products", {"query": "يوريا", "category": "fertilizer", "limit": 5})
# → يختار أفضل سعر

mcp_call(
    "market_create_procurement",
    {
        "tenant_id": tenant,
        "field_id": "field_A3",
        "items": [{"product_name": "Urea 46%", "quantity": 2000, "unit": "kg"}],
    },
)
# → order_id + status (draft أو approved)
```

---

## 📱 تكامل Flutter

```dart
// lib/services/market_service.dart
class MarketService {
  final String baseUrl = "http://sahool-market-mcp:8000";

  Future<List<Product>> searchProducts(String query) async {
    final res = await http.get(Uri.parse("$baseUrl/v1/products?q=$query"));
    final data = jsonDecode(res.body);
    return (data['products'] as List).map((e) => Product.fromJson(e)).toList();
  }

  Future<ProcurementOrder> createOrder(List<CartItem> items) async {
    final res = await http.post(
      Uri.parse("$baseUrl/v1/procurement"),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'tenant_id': tenantId,
        'items': items.map((i) => i.toJson()).toList(),
      }),
    );
    return ProcurementOrder.fromJson(jsonDecode(res.body));
  }
}
```

---

## 🛡️ الأمان

- ✅ **RLS:** كل الجداول محمية بـ `tenant_isolation`.
- ✅ **JWT:** يمكن إضافة `Depends(verify_token)` على REST endpoints (مُجهز في الكود).
- ✅ **Validation:** Pydantic v2 على جميع inputs.
- ✅ **SQL Injection:** استخدام `asyncpg` مع parameterized queries فقط.

---

## 📊 Seed Data (بيانات أولية)

| المورد | المنتج | السعر | المخزون |
|--------|--------|-------|---------|
| شركة أسمدة اليمن | يوريا 46% | 0.45 USD/kg | 50,000 kg |
| شركة أسمدة اليمن | NPK 15-15-15 | 0.52 USD/kg | 30,000 kg |
| تجارة بذور الخليج | بذور قمح صنعاء | 1.20 USD/kg | 10,000 kg |
| سينجنتا الشرق الأوسط | جلايفوسات 41% | 8.50 USD/liter | 2,000 L |

---

## 🔮 التحسينات المستقبلية

1. **Price Scraper:** ربط بـ `market_price_history` لجلب أسعار السلع من مواقع عالمية (FAO, World Bank).
2. **Negotiation Bot:** وكيل MCP يتفاوض تلقائياً مع موردين عبر email/ WhatsApp API.
3. **Logistics Integration:** ربط طلبات الشراء بشركات شحن (DHL, Aramex APIs).
4. **Payment Gateway:** دمج Stripe/ Paymob/ Telr للدفع الإلكتروني.
5. **Mobile Scanner:** `flutter_barcode_scanner` لمسح QR على شحنات الموردين.

---

**الخلاصة:** نظام السوق في SAHOOL v9.1 أصبح **كاملاً وقابلاً للتشغيل** — يغطي المشتريات (B2B procurement)، سوق المحاصيل (crop marketplace)، تتبع الأسعار، والتحليلات. جاهز للربط مع Odoo ERP و Flutter App.
