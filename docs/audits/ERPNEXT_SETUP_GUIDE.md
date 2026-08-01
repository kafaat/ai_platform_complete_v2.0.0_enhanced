# دليل تهيئة ERPNext لـSAHOOL (نشر + إعداد زراعي)

أكملتُ اللازم: حاوية MariaDB + معماريّة Frappe الكاملة + التهيئة. هذا الدليل
يشرح التشغيل الفعلي على جهازك (الكود جاهز، التنفيذ الحيّ يحتاج بيئتك).

## لماذا ملفّ منفصل؟ (تصحيح مهمّ)
ERPNext **ليس حاوية واحدة**. حسب توثيق Frappe الرسمي، يحتاج معماريّة متعدّدة
الخدمات. الخدمة المبسّطة التي كانت في compose الرئيسي كانت **ستفشل** (Frappe
يحتاج bench كامل + إنشاء موقع). لذا فصلتُه في `docker-compose.erpnext.yml`
بالطريقة الصحيحة: 11 خدمة.

## المعماريّة (docker-compose.erpnext.yml)
| الخدمة | الدور |
|--------|-------|
| erpnext-db | MariaDB 10.6 (ERPNext يتطلّبها لا PostgreSQL) |
| erpnext-redis-cache/queue | Redis منفصلان (توصية Frappe) |
| erpnext-configurator | يكتب common_site_config ثمّ يخرج |
| erpnext-create-site | ينشئ الموقع + يثبّت erpnext (مرّة واحدة) |
| erpnext-backend | الخادم الخلفي (gunicorn) |
| erpnext-frontend | nginx — منفذ 8000 |
| erpnext-websocket | Socket.IO (real-time) |
| erpnext-queue-short/long | عمّال الطابور (RQ) |
| erpnext-scheduler | المهام المجدولة |

## خطوات التشغيل (على جهازك)
### ١. اضبط .env
```
ERP_PROVIDER=erpnext
ERPNEXT_VERSION=v15.45.5
ERPNEXT_SITE=sahool.localhost
ERPNEXT_DB_PASSWORD=<كلمة قويّة>
ERPNEXT_ADMIN_PASSWORD=<كلمة قويّة>
```

### ٢. شغّل النظام الرئيسي أوّلاً (لإنشاء الشبكة)
```powershell
docker compose -f docker-compose.v9.yml --env-file .env up -d
```

### ٣. شغّل ERPNext (يشارك شبكة sahool-internal)
```powershell
docker compose -f docker-compose.erpnext.yml --env-file .env up -d
```
أوّل تشغيل: create-site تُنشئ الموقع وتثبّت erpnext (قد يأخذ دقائق).

### ٤. ولّد مفاتيح API
- ادخل http://localhost:8000 (المستخدم: Administrator، كلمة المرور: ADMIN)
- User → API Access → Generate Keys → انسخ key + secret
- ضعهما في .env: ERPNEXT_API_KEY, ERPNEXT_API_SECRET
- أعد تشغيل odoo-bridge: `docker compose restart sahool-odoo-bridge`

### ٥. تحقّق من التبديل
```powershell
curl http://localhost:8126/v1/erp/provider
# يُفترض: {"selected":"erpnext","active_provider":"erpnext",...}
```

## ═══ التهيئة الزراعيّة ═══
### أ) ثبّت وحدة الزراعة (مفتوحة المصدر GPL)
داخل حاوية backend:
```powershell
docker compose -f docker-compose.erpnext.yml exec erpnext-backend bash
bench get-app https://github.com/frappe/agriculture
bench --site sahool.localhost install-app agriculture
```
الوحدة تضيف: المحاصيل، الأراضي، تحليل التربة/المياه/الطقس، الأمراض، الأسمدة.

### ب) فعّل الوحدات الأساسيّة (من الواجهة)
- Stock (المخزون) · Accounts (المحاسبة) · Buying (المشتريات)
- فعّل "Perpetual Inventory" للتتبّع الدقيق

### ج) أنشئ فئات منتجات زراعيّة (تطابق LedgerKind)
Stock → Item Group → أنشئ:
| فئة ERPNext | LedgerKind المطابق |
|-------------|---------------------|
| بذور Seeds | SEED |
| أسمدة Fertilizer | FERTILIZER |
| مبيدات Pesticide | PESTICIDE |
| عمالة Labor | LABOR |
| وقود Fuel | FUEL |
| ريّ Water | WATER |
| معدّات Equipment | EQUIPMENT |
| نقل Transport | TRANSPORT |

### د) المحاسبة التحليليّة لتكاليف الحقل
- فعّل Cost Centers (مركز تكلفة لكلّ حقل)
- الجسر يدفع تكاليف SAHOOL → ERPNext عبر push_field_cost

#### تفعيل push_field_cost (ربط حسابات قيد اليوميّة)
`push_field_cost` يبني قيد Journal Entry متوازناً (مدين=دائن، شرط Frappe).
لا يعمل حتّى تُضبط الحسابات الخاصّة بتثبيتك (لا تُفبرك أرقام حسابات). أضِف
لـ.env بعد إنشاء الحسابات في دليل حسابات ERPNext (Chart of Accounts):

```bash
# الحساب المدين (مصروف الحقل) — مثال (بدّله بحسابك الفعلي):
ERPNEXT_EXPENSE_ACCOUNT="Farm Operating Expenses - SAHOOL"
# الحساب الدائن (نقد/دائنون):
ERPNEXT_CREDIT_ACCOUNT="Cash - SAHOOL"
# الشركة (إلزامي في Frappe):
ERPNEXT_COMPANY="SAHOOL Agriculture"
# مركز التكلفة (اختياري — للمحاسبة التحليليّة لكلّ حقل):
ERPNEXT_COST_CENTER="Al-Jawf Fields - SAHOOL"
```

- المصادقة: `ERPNEXT_API_KEY:ERPNEXT_API_SECRET` في رأس `Authorization: token`
  (من User → Settings → API Access → Generate Keys).
- بلا الحسابات الثلاثة الإلزاميّة (expense/credit/company) → push_field_cost
  يُعلِن NotImplementedError بصدق (لا محاولة فاشلة، لا فبركة).
- تحقّق بعد الضبط: التكلفة تظهر في Accounting → Journal Entry، والمجموع
  المدين = الدائن.

## التبديل بين المزوّدات (مرونة كاملة)
| ERP_PROVIDER | الأمر |
|--------------|-------|
| odoo | `--profile odoo` على compose الرئيسي |
| erpnext | `docker-compose.erpnext.yml` منفصل |
| none | لا شيء — النظام يعمل بـfarm_ledger المحلّي |

## ملاحظة صدق
- المعماريّة قياسيّة من **توثيق Frappe الرسمي** (بحثتُ وتحقّقت).
- **لم أختبرها حيّاً** — تحتاج Docker + تنزيل صور Frappe على جهازك (بيئتي بلا
  شبكة/docker). التواقيع والإعداد صحيحة بنيويّاً.
- تثبيت وحدة الزراعة وإنشاء الفئات يتمّ **عبر واجهة/bench على جهازك** — لا
  أزيّف ملفّات وحدة.
- تحقّق من آخر إصدار `ERPNEXT_VERSION` مستقرّ قبل التشغيل.
