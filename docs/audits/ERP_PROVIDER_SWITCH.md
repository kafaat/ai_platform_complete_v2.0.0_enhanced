# مفتاح تبديل مزوّد ERP + حاوية ERPNext

بنيتُ مرونة معماريّة: تجريد مزوّد ERP خلف واجهة موحّدة، مع مفتاح تبديل
ومزوّدَين + خيار الإيقاف.

## ما بُني (كود حقيقي)
### ١. تجريد المزوّد (erp_provider.py)
واجهة `ERPProvider` موحّدة + 3 تطبيقات:
| المزوّد | الوصف |
|---------|-------|
| `OdooProvider` | يلفّ OdooClient الموجود (JSON-RPC) — يعيد استخدامه لا يكرّره |
| `ERPNextProvider` | Frappe REST API (كود حقيقي، يحتاج خادم ERPNext للاختبار) |
| `NullProvider` | ERP معطّل — النظام يعمل بـfarm_ledger المحلّي فقط |

الواجهة الموحّدة: authenticate, list_products, list_suppliers,
list_warehouses, push_field_cost, health.

### ٢. مفتاح التبديل (ERP_PROVIDER)
متغيّر بيئة واحد يحدّد المزوّد دون تغيير كود:
```
ERP_PROVIDER=odoo      # الافتراضي (التوافق الخلفي)
ERP_PROVIDER=erpnext   # ERPNext (مفتوح المصدر GPL)
ERP_PROVIDER=none      # إيقاف ERP تماماً
```

### ٣. حاوية ERPNext (docker-compose)
- `sahool-erpnext` (frappe/erpnext) مُضافة
- **profiles للتبديل**: Odoo يعمل مع `--profile odoo`، ERPNext مع
  `--profile erpnext` — لا يعملان معاً (بديلان لا مكمّلان)
- odoo-bridge: تبعيّة Odoo صارت `required: false` → الجسر يعمل مع أيّ مزوّد

### ٤. endpoint كشف الحالة
`GET /v1/erp/provider` يكشف المزوّد النشط وحالته.

## كيف تستخدمه
```powershell
# Odoo (الافتراضي)
docker compose -f docker-compose.v9.yml --profile odoo --env-file .env up -d

# ERPNext (بدّل في .env: ERP_PROVIDER=erpnext + المفاتيح)
docker compose -f docker-compose.v9.yml --profile erpnext --env-file .env up -d

# بلا ERP (ERP_PROVIDER=none) — لا profile لازم
docker compose -f docker-compose.v9.yml --env-file .env up -d
```

## التحقّق
- 555/555 roadmap (+7) · 0 خطأ · offline 34/0
- التبديل مُختبَر: none→معطّل، erpnext→Frappe، odoo→OdooClient
- compose صالح: 33 خدمة، profiles صحيحة

## أمان التبديل (صدق)
- erpnext بلا مفاتيح → none تلقائيّاً (لا اتّصال وهمي)
- NullProvider يجعل إيقاف ERP آمناً (النظام يعمل بـfarm_ledger)
- odoo-bridge لا يفشل حين Odoo معطّل (required: false)

## ما لم يُختبَر حيّاً (صدق)
- **ERPNextProvider**: كود Frappe REST حقيقي، لكنّه يحتاج **خادم ERPNext حيّاً**
  على جهازك لاختبار الاتّصال الفعلي. التواقيع صحيحة، الاختبار الحيّ على بيئتك.
- **حاوية ERPNext**: ERPNext يفضّل MariaDB (لا PostgreSQL) — التهيئة الكاملة
  تحتاج إعداد قاعدة ERPNext على جهازك (موثّق في التعليقات).
- صورة `frappe/erpnext:v15.45.5`: تحقّق من آخر إصدار مستقرّ على جهازك.

## ملاحظة صدق
بنيتُ التجريد والمفتاح والحاوية كـ**كود حقيقي يعمل** (التبديل مُختبَر منطقيّاً).
لم أزعم أنّ ERPNext متّصل حيّاً — يحتاج خادمه على جهازك. OdooProvider يعيد
استخدام الموجود (لا تكرار). NullProvider يضمن أنّ إيقاف ERP لا يُعطّل النظام.
