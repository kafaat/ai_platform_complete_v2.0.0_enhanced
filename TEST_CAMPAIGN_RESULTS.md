# نتائج حملة الاختبار — Build · Operational · E2E · Smoke

بيئة: Python 3.11، PostgreSQL 16 + PostGIS، Redis 7، Node 22. سكربتات:
`verify_review_fixes.py`، `services/sahool-platform/smoke_e2e_test.py`.

## ① اختبارات البناء (Build)

| المكوّن | النتيجة |
|---------|---------|
| ترجمة Python (`py_compile` لكل الخدمات) | ✅ 0 خطأ |
| استيراد الخدمات (smoke) | ✅ 7 تستورد نظيفًا · 7 تفشل فقط على تبعيات اختياريّة غير مثبّتة (bcrypt/PIL/aiomqtt/langchain/edge_tts/python-multipart) — لا أخطاء كود. **edge-inference يتجاوز C3 (lifespan) ويصل لاستيراد PIL** ⇒ إصلاح C3 صحيح |
| الواجهة — بناء الإنتاج (`vite build` = `build:docker` في Dockerfile) | ✅ ينجح → `dist/` 1.3M |
| الواجهة — `npm install` (صارم) | ❌ **ERESOLVE**: `lucide-react@0.376` يدعم React 18 فقط بينما يُسحب React 19 (يلزم `--legacy-peer-deps`) |
| الواجهة — `npm run build` (`tsc && vite`) | ❌ **2441 خطأ TypeScript** (الفحص النوعي معطّل؛ الإنتاج يتخطّى tsc) |

## ② اختبارات تشغيلية — الترحيلات (Operational)

طُبِّقت الـ18 ترحيلًا على قاعدة **جديدة** فعليّة:

- **قبل إصلاحاتي: 11/18 فقط** (بناء قاعدة إنتاج جديدة مكسور).
- **بعد إصلاحاتي: ✅ 18/18 تُطبَّق نظيفًا** — 40 جدولًا، **26 بـRLS** مفعّل.
- **C2 مُتحقَّق عمليًّا**: RLS على `field_boundaries, soil_readings, events, commands, field_lifecycle, ndvi_timeseries, edge_results`.

### 10 أخطاء ترحيل أصلحتُها (كانت تكسر التمهيد):
| الملف | الخطأ | الإصلاح |
|-------|-------|---------|
| `v9_new_tables.sql` ×3 | تعليق `-- FIX` ابتلع فاصلة إنهاء العمود ⇒ syntax error | نقل الفاصلة قبل التعليق |
| `v9_market.sql` | نفس نمط التعليق-يبتلع-الفاصلة | نقل الفاصلة |
| `v9_foundation.sql` | `SET search_path` داخل جسم الدالّة قبل `BEGIN` (PL/pgSQL غير صالح) | نقله لترويسة الدالّة |
| `v9_odoo_bridge.sql` | `INTEGER (50)` صياغة غير صالحة؛ + from/to_state نصّيّة لا عدديّة | `VARCHAR(50)` مطابقة للـINSERT |
| `init_v8.sql` | `field_boundaries.field_id` بلا قيد فريد رغم FKs إليه | `UNIQUE` |
| `v9_new_tables.sql` | `EXCEPTION` مباشرةً في `LOOP` بلا `BEGIN…END` | تغليف بـbegin/end |
| RLS loops (market/automation/new_tables/odoo) | تُفعّل RLS على جداول غير موجودة/بلا tenant_id | حارس `to_regclass` + فحص عمود tenant_id |
| فهارس (odoo/new_tables) | على جداول تُنشأ لاحقًا/غائبة | تغليف بفحص وجود الجدول |
| `MANIFEST.txt` | `v9_lifecycle_occurred_at` قبل v10 المُنشئ للجدول | نقله بعد v10 |

## ③ E2E + Smoke — منصّة حيّة مع Postgres حقيقي

`smoke_e2e_test.py` عبر TestClient (lifespan يتصل بالقاعدة الفعليّة): **11/11 ✅**

| الاختبار | النتيجة |
|----------|---------|
| SMOKE `GET /healthz` · `/readyz` (pool جاهز) | ✅ 200 |
| E2E تسجيل دخول (dev) → JWT | ✅ |
| E2E **H8 حيّ**: `/confidence/ndvi` بتاريخ ساذج بلا إزاحة → **200** (كان 500) | ✅ |
| E2E **H8 حيّ**: تاريخ فاسد → **422** (لا 500) | ✅ |
| E2E تفويض: بلا توكن → 401/403 | ✅ |
| E2E نقطة DB حيّة (pool حقيقي، لا 503) | ✅ |

## نتائج إضافيّة مكتشَفة أثناء الاختبار (موثّقة، غير مُصلَحة بعد)
- **OpenAPI/`/openapi.json` يفشل بـ500**: نموذج `OnboardingSubmitRequest` (forward-ref) يحتاج `model_rebuild()` ⇒ `export_openapi.py` سيفشل أيضًا. (ديْن — يحتاج تتبّع المرجع الأمامي.)
- **الواجهة**: tsc معطّل (2441) و`npm install` يحتاج `--legacy-peer-deps` — ديون بناء (الإنتاج يعمل عبر vite).

## ملاحظة صدق
الترحيلات والـe2e نُفّذت على **Postgres 16 + PostGIS حقيقي** في هذه البيئة.
بعض الخدمات لم تُستورَد لغياب تبعيّات اختياريّة (لم تُثبَّت) — لا لأخطاء كود.
